import AppKit
import Foundation

private struct ReleaseManifest: Decodable {
    let product: String
    let localHostname: String
    let localPort: Int
    let dataDirectoryName: String
}

private struct ActivationState: Decodable {
    let schemaVersion: Int
    let hostname: String
    let port: Int
    let token: String
}

private struct ActivationResponse: Decodable {
    let url: String
}

@MainActor
final class ReachCutLauncher: NSObject, NSApplicationDelegate {
    private let agentIdentifier = "__REACHCUT_AGENT_ID__"
    private var manifest: ReleaseManifest?
    private var progressWindow: NSWindow?
    private var statusLabel: NSTextField?
    private var launchInProgress = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        beginLaunch()
    }

    func applicationShouldHandleReopen(
        _ sender: NSApplication,
        hasVisibleWindows flag: Bool
    ) -> Bool {
        beginLaunch()
        return true
    }

    private func beginLaunch() {
        guard !launchInProgress else {
            showProgress(message: "ReachCut is still starting…")
            return
        }

        do {
            manifest = try loadManifest()
        } catch {
            showFailure("The ReachCut installation is incomplete.\n\n\(error.localizedDescription)")
            return
        }

        launchInProgress = true
        showProgress(message: "Starting ReachCut…")

        Task {
            do {
                try await ensureServiceIsReady()
                updateStatus("Opening ReachCut in your browser…")
                try await activateBrowser()
                try await Task.sleep(for: .milliseconds(350))
                await MainActor.run { NSApp.terminate(nil) }
            } catch {
                await MainActor.run {
                    self.launchInProgress = false
                    self.showFailure(
                        "ReachCut could not start.\n\n\(error.localizedDescription)"
                    )
                }
            }
        }
    }

    private func loadManifest() throws -> ReleaseManifest {
        guard let resources = Bundle.main.resourceURL else {
            throw NSError(
                domain: "ReachCutLauncher",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Application resources were not found."]
            )
        }
        let url = resources
            .appendingPathComponent("app", isDirectory: true)
            .appendingPathComponent("reachcut-package.json")
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(ReleaseManifest.self, from: data)
    }

    private func ensureServiceIsReady() async throws {
        if await serviceIsReady() { return }

        updateStatus("Starting the local ReachCut service…")
        try startLaunchAgent()

        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline {
            if await serviceIsReady() { return }
            try await Task.sleep(for: .milliseconds(500))
        }
        throw NSError(
            domain: "ReachCutLauncher",
            code: 2,
            userInfo: [
                NSLocalizedDescriptionKey:
                    "The local service did not become ready within 90 seconds."
            ]
        )
    }

    private func startLaunchAgent() throws {
        let userDomain = "gui/\(getuid())"
        let service = "\(userDomain)/\(agentIdentifier)"
        let systemPlist = "/Library/LaunchAgents/\(agentIdentifier).plist"
        let plist = if FileManager.default.fileExists(atPath: systemPlist) {
            systemPlist
        } else {
            try createStandaloneLaunchAgent()
        }

        _ = run(executable: "/bin/launchctl", arguments: ["bootout", service])
        _ = run(
            executable: "/bin/launchctl",
            arguments: ["bootstrap", userDomain, plist]
        )
        let result = run(
            executable: "/bin/launchctl",
            arguments: ["kickstart", "-k", service]
        )
        if result != 0 {
            throw NSError(
                domain: "ReachCutLauncher",
                code: 3,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "macOS could not start the ReachCut login service (launchctl exit \(result))."
                ]
            )
        }
    }

    private func createStandaloneLaunchAgent() throws -> String {
        guard let manifest,
              let resources = Bundle.main.resourceURL else {
            throw NSError(
                domain: "ReachCutLauncher",
                code: 8,
                userInfo: [NSLocalizedDescriptionKey: "Application resources were not found."]
            )
        }
        let appRoot = resources.appendingPathComponent("app", isDirectory: true)
        let node = appRoot.appendingPathComponent("runtime/node").path
        let agent = appRoot.appendingPathComponent("scripts/reachcut-agent.mjs").path
        let directory = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support", isDirectory: true)
            .appendingPathComponent(manifest.dataDirectoryName, isDirectory: true)
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true
        )
        let plistURL = directory.appendingPathComponent("launcher-agent.plist")
        let propertyList: [String: Any] = [
            "Label": agentIdentifier,
            "ProgramArguments": [node, agent, "--production", "--no-browser"],
            "RunAtLoad": true,
            "KeepAlive": ["SuccessfulExit": false],
            "ThrottleInterval": 5,
            "ProcessType": "Interactive",
        ]
        let data = try PropertyListSerialization.data(
            fromPropertyList: propertyList,
            format: .xml,
            options: 0
        )
        try data.write(to: plistURL, options: .atomic)
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: plistURL.path
        )
        return plistURL.path
    }

    private func run(executable: String, arguments: [String]) -> Int32 {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus
        } catch {
            return -1
        }
    }

    private func serviceIsReady() async -> Bool {
        guard let manifest,
              let url = URL(
                string: "http://\(manifest.localHostname):\(manifest.localPort)/__reachcut/health"
              ) else {
            return false
        }
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 2
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }

    private func activateBrowser() async throws {
        guard let manifest else { return }
        let stateURL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support", isDirectory: true)
            .appendingPathComponent(manifest.dataDirectoryName, isDirectory: true)
            .appendingPathComponent("agent-activation.json")

        let deadline = Date().addingTimeInterval(5)
        var lastError: Error?
        while Date() < deadline {
            do {
                let stateData = try Data(contentsOf: stateURL)
                let state = try JSONDecoder().decode(ActivationState.self, from: stateData)
                guard state.schemaVersion == 1,
                      state.hostname == manifest.localHostname,
                      state.port == manifest.localPort,
                      state.token.count >= 32 else {
                    throw NSError(
                        domain: "ReachCutLauncher",
                        code: 4,
                        userInfo: [
                            NSLocalizedDescriptionKey:
                                "The local activation state belongs to another ReachCut profile."
                        ]
                    )
                }

                guard let activationURL = URL(
                    string: "http://\(manifest.localHostname):\(manifest.localPort)/__reachcut/activate"
                ) else {
                    throw URLError(.badURL)
                }
                var request = URLRequest(url: activationURL)
                request.httpMethod = "POST"
                request.timeoutInterval = 3
                request.setValue(state.token, forHTTPHeaderField: "X-ReachCut-Activation")
                let (data, response) = try await URLSession.shared.data(for: request)
                guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                    throw NSError(
                        domain: "ReachCutLauncher",
                        code: 5,
                        userInfo: [NSLocalizedDescriptionKey: "The local service rejected browser activation."]
                    )
                }
                let activation = try JSONDecoder().decode(ActivationResponse.self, from: data)
                guard let browserURL = URL(string: activation.url),
                      browserURL.scheme == "http",
                      browserURL.host == manifest.localHostname,
                      browserURL.port == manifest.localPort,
                      browserURL.path == "/__reachcut/bootstrap",
                      browserURL.fragment?.hasPrefix("token=") == true,
                      NSWorkspace.shared.open(browserURL) else {
                    throw NSError(
                        domain: "ReachCutLauncher",
                        code: 6,
                        userInfo: [NSLocalizedDescriptionKey: "macOS could not open the default browser."]
                    )
                }
                return
            } catch {
                lastError = error
                try await Task.sleep(for: .milliseconds(250))
            }
        }
        throw lastError ?? NSError(
            domain: "ReachCutLauncher",
            code: 7,
            userInfo: [NSLocalizedDescriptionKey: "Browser activation timed out."]
        )
    }

    @MainActor
    private func updateStatus(_ message: String) {
        statusLabel?.stringValue = message
    }

    @MainActor
    private func showProgress(message: String) {
        if progressWindow == nil {
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 390, height: 150),
                styleMask: [.titled],
                backing: .buffered,
                defer: false
            )
            window.title = manifest?.product ?? "ReachCut"
            window.isReleasedWhenClosed = false
            window.center()

            let indicator = NSProgressIndicator()
            indicator.style = .spinning
            indicator.controlSize = .regular
            indicator.startAnimation(nil)

            let label = NSTextField(labelWithString: message)
            label.alignment = .center
            label.font = .systemFont(ofSize: 15, weight: .medium)
            label.maximumNumberOfLines = 2
            statusLabel = label

            let stack = NSStackView(views: [indicator, label])
            stack.orientation = .vertical
            stack.alignment = .centerX
            stack.spacing = 18
            stack.translatesAutoresizingMaskIntoConstraints = false
            window.contentView?.addSubview(stack)
            NSLayoutConstraint.activate([
                stack.centerXAnchor.constraint(equalTo: window.contentView!.centerXAnchor),
                stack.centerYAnchor.constraint(equalTo: window.contentView!.centerYAnchor),
                label.widthAnchor.constraint(lessThanOrEqualToConstant: 330),
            ])
            progressWindow = window
        } else {
            statusLabel?.stringValue = message
        }

        progressWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @MainActor
    private func showFailure(_ message: String) {
        progressWindow?.orderOut(nil)
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = "ReachCut could not open"
        alert.informativeText = message
        alert.addButton(withTitle: "Try Again")
        alert.addButton(withTitle: "Quit")
        NSApp.activate(ignoringOtherApps: true)
        if alert.runModal() == .alertFirstButtonReturn {
            beginLaunch()
        } else {
            NSApp.terminate(nil)
        }
    }
}

@main
struct ReachCutLauncherMain {
    @MainActor
    static func main() {
        let application = NSApplication.shared
        let delegate = ReachCutLauncher()
        application.delegate = delegate
        application.run()
    }
}
