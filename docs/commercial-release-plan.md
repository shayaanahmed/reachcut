# ReachCut commercial release plan

This plan takes ReachCut from its current developer-operated Docker setup to a private,
paid pilot that can be installed on one authorized customer machine without sharing the
Git repository. Follow the milestones in order and do not begin a public launch until
the pilot release gates at the end of this document are satisfied.

The first commercial target is **ReachCut Private Edition**:

- One customer license activates one machine.
- ReachCut and customer media remain on that machine.
- Customers receive an installer and private Docker images, not the repository.
- The first three to five customers receive assisted installation and support.
- Payment and license creation may be handled manually during the pilot.

## Current status

| Area                                | Status                          | Evidence or next action                     |
| ----------------------------------- | ------------------------------- | ------------------------------------------- |
| Core product                        | Working development application | Local API and web checks pass               |
| API tests                           | Passing                         | 114 tests passed on 2026-10-08              |
| Web tests                           | Passing                         | 26 tests passed on 2026-10-08               |
| Production image builds             | Passing locally                 | API and web images both built successfully  |
| CircleCI configuration              | Committed and pushed            | Connect the repository and run the pipeline |
| Private image publishing            | Not implemented                 | Milestone 2                                 |
| Commercial runtime images           | Not implemented                 | Milestone 3                                 |
| Backup and upgrade safety           | Not release-tested              | Milestone 4                                 |
| Machine licensing                   | Not implemented                 | Milestone 5                                 |
| Customer installer and updater      | Not implemented                 | Milestone 6                                 |
| Customer onboarding and diagnostics | Not implemented                 | Milestone 7                                 |
| Commercial and legal material       | Not complete                    | Milestone 8                                 |
| Paid pilot                          | Not started                     | Milestone 10                                |

## How to use this plan

1. Work on only one milestone at a time unless a section explicitly allows parallel work.
2. Check an item only after its result has been demonstrated, not merely implemented.
3. Record important choices in the decision log at the end of this document.
4. Record every release candidate in the release record.
5. Do not put passwords, tokens, private keys, or customer information in this document.
6. Treat every exit gate as mandatory unless the exception is documented and accepted.

## Release flow

```text
Private source repository
        |
        v
CircleCI checks and tests
        |
        v
Versioned release images
        |
        v
Security scan and signature
        |
        v
Private container registry
        |
        v
Licensed customer installer
        |
        v
One isolated customer machine
```

## Milestone 0: Confirm the pilot product

**Purpose:** Decide what the first release supports before building distribution and
licensing around it.

### Product decisions

- [ ] Select the first supported operating system.
  - Windows 11 x86-64, macOS Apple Silicon, or Ubuntu Linux x86-64.
  - Select the platform used by the first pilot customers.
- [ ] Decide whether Docker Desktop or Docker Engine is installed by the customer or by
      the ReachCut installer.
- [ ] Define minimum and recommended CPU, RAM, GPU, and disk requirements.
- [ ] Decide whether the pilot requires an internet connection.
- [ ] Confirm one license permits one active machine.
- [ ] Confirm the offline licensing grace period. The proposed starting value is seven
      days.
- [ ] Define which features are included in the pilot.
- [ ] Decide whether social publishing is included or treated as an assisted beta.
- [ ] Choose the private container registry. The proposed starting choice is GitHub
      Container Registry.
- [ ] Choose whether to buy a licensing service or build one. The proposed pilot choice
      is a managed licensing service.

### Initial hardware document

Create a supported-hardware section in the customer installation guide containing:

- [ ] Supported operating-system version
- [ ] Supported CPU architecture
- [ ] Minimum and recommended memory
- [ ] Required free disk space
- [ ] Supported GPU and acceleration modes
- [ ] Required Docker version
- [ ] Internet and firewall requirements
- [ ] Approximate model download sizes
- [ ] Known unsupported configurations

### Exit gate

- [ ] The first supported platform is named explicitly.
- [ ] The first three pilot customers can satisfy the hardware requirements.
- [ ] The license and offline-use rules are written down.
- [ ] The included pilot features are written down.

## Milestone 1: Activate the validation pipeline

**Purpose:** Ensure every change is checked automatically before it can become a release.

The initial pipeline is defined in `.circleci/config.yml`. It runs API and web quality
jobs on branches and verifies the production Docker builds after changes reach `main`.

### Connect CircleCI

- [x] Add `.circleci/config.yml`.
- [x] Add the CircleCI operating guide in `docs/circleci.md`.
- [x] Verify API checks and tests locally.
- [x] Verify web checks and tests locally.
- [x] Verify both production image builds locally.
- [x] Commit the CircleCI files.
- [x] Push them to the private repository.
- [ ] Connect the repository in CircleCI.
- [ ] Run the first pipeline from `main`.
- [ ] Confirm `api-quality` passes.
- [ ] Confirm `web-quality` passes.
- [ ] Confirm `docker-build` passes on `main`.
- [ ] Open a test pull request and confirm CircleCI reports its status to the Git provider.
- [ ] Protect `main` and require the CircleCI validation check before merging.

### Exit gate

- [ ] A deliberately failing test blocks the pull request.
- [ ] Fixing the test allows the pull request to pass.
- [ ] A successful merge to `main` builds both production images.
- [ ] No deployment or production credentials are available to ordinary validation jobs.

## Milestone 2: Publish internal release images

**Purpose:** Turn a version tag into immutable, private artifacts without distributing
them to customers yet.

### Configure the private registry

- [ ] Create the private API image package.
- [ ] Create the private web image package.
- [ ] Create a dedicated CI identity with permission to push only ReachCut packages.
- [ ] Store the registry username and push token in a restricted CircleCI context.
- [ ] Confirm normal validation jobs cannot access the release context.
- [ ] Decide who is allowed to pull internal images.
- [ ] Enable registry audit logging where available.

Proposed image names:

```text
ghcr.io/REACHCUT_OWNER/reachcut-api
ghcr.io/REACHCUT_OWNER/reachcut-web
```

### Define release versions

Use semantic versions with a pilot suffix:

```text
v0.1.0-internal.1
v0.1.0-pilot.1
v0.1.0-pilot.2
v0.1.0
```

Do not publish customer installations from `latest`. Use a version and immutable digest.

### Add the release workflow

- [ ] Trigger the release workflow only for approved version tags.
- [ ] Re-run API and web checks in the release workflow.
- [ ] Build the API image.
- [ ] Build the web image.
- [ ] Tag both images with the release version.
- [ ] Generate a software bill of materials for both images.
- [ ] Scan both images for vulnerabilities.
- [ ] Sign both images.
- [ ] Push both images to the private registry.
- [ ] Record both immutable image digests.
- [ ] Store the scan reports and release manifest as CircleCI artifacts.
- [ ] Prevent publishing if checks, tests, scans, or signing fail.

The release manifest should contain at least:

```json
{
  "version": "0.1.0-internal.1",
  "api_image": "ghcr.io/REACHCUT_OWNER/reachcut-api@sha256:...",
  "web_image": "ghcr.io/REACHCUT_OWNER/reachcut-web@sha256:...",
  "created_at": "ISO-8601 timestamp",
  "source_revision": "Git commit SHA"
}
```

### Internal release test

- [ ] Create tag `v0.1.0-internal.1`.
- [ ] Confirm CircleCI publishes both images.
- [ ] Pull both images using an authorized test identity.
- [ ] Confirm an unauthorized identity cannot pull either image.
- [ ] Verify the signatures.
- [ ] Start ReachCut using only registry images and persistent volumes.
- [ ] Process a test project from upload through final export.

### Exit gate

- [ ] A Git tag produces signed, private, immutable images.
- [ ] The release manifest identifies the exact source revision and image digests.
- [ ] ReachCut runs without access to the source repository.
- [ ] Creating images does not distribute them to customers automatically.

## Milestone 3: Create commercial runtime images

**Purpose:** Reduce the code and tooling exposed inside customer images and produce a
minimal supported runtime.

A private registry prevents unauthorized downloads, but a customer administrator can
export an image after pulling it. Image privacy is not a substitute for runtime licensing
or source-hardening.

### Separate development and release images

- [ ] Keep developer-friendly Dockerfiles for local development.
- [ ] Add explicit commercial release Dockerfiles or release build stages.
- [ ] Remove tests, fixtures, caches, and development dependencies from release images.
- [ ] Remove source maps from the production web build.
- [ ] Verify `.git`, local `.env` files, and developer metadata are excluded.
- [ ] Verify no credentials exist in any image layer.
- [ ] Run both images as non-root users.
- [ ] Use a read-only filesystem except for declared volumes and temporary directories.
- [ ] Pin release base-image versions.

### Protect proprietary backend code

- [ ] Run a compilation feasibility experiment for the Python API.
- [ ] Verify compiled startup, FastAPI routing, SQLAlchemy, Pydantic, provider loading,
      OpenCV, Faster Whisper, FFmpeg, and health checks.
- [ ] Document any dynamic imports or data files that the compiler must include.
- [ ] Remove plain proprietary `.py` files from the final commercial image.
- [ ] Confirm the compiled image completes the entire media workflow.

Frontend JavaScript is delivered to the browser and remains inspectable. Do not place
secrets, signing keys, or license-enforcement decisions in the frontend.

### Exit gate

- [ ] Release images contain no repository or development-only material.
- [ ] Proprietary API modules are not shipped as plain source files.
- [ ] No secret is present in image configuration, history, environment, or layers.
- [ ] Both images pass the agreed vulnerability threshold.
- [ ] The release images process a representative video successfully.

## Milestone 4: Make customer data upgrade-safe

**Purpose:** Ensure an application update cannot silently destroy projects, credentials,
or exports.

### Database migrations

- [ ] Replace startup-only schema creation with versioned migration execution.
- [ ] Record the installed schema version.
- [ ] Create the first baseline migration.
- [ ] Create automated migration tests.
- [ ] Back up the database before an upgrade.
- [ ] Stop the upgrade if backup creation fails.
- [ ] Define recovery behavior for a failed migration.

### Backup and restore

- [ ] Define exactly which data belongs in a ReachCut backup.
- [ ] Include the database, project media, assets, exports, credential files, and the
      credential-encryption key where appropriate.
- [ ] Add a manual backup command.
- [ ] Add a restore command with integrity validation.
- [ ] Add configurable backup and media locations.
- [ ] Add free-space warnings.
- [ ] Add temporary-artifact cleanup and retention controls.
- [ ] Make project deletion behavior explicit.

### Upgrade test

- [ ] Install version A on a clean machine.
- [ ] Create and render a project.
- [ ] Create a backup.
- [ ] Upgrade to version B.
- [ ] Verify the project, clip, export, and social-account metadata.
- [ ] Restore the backup to a clean installation.
- [ ] Verify the restored project and export.

### Exit gate

- [ ] Every release has a tested upgrade path from the previous supported version.
- [ ] Backup and restore work on a clean supported machine.
- [ ] A failed upgrade can return to the previous working version.

## Milestone 5: Add one-machine licensing

**Purpose:** Prevent ordinary license sharing and copied installations while allowing
legitimate customers to recover or move their license.

### Licensing policy

- [ ] Create a product and one-machine policy in the selected licensing service.
- [ ] Define activation, refresh, expiration, suspension, and deactivation behavior.
- [ ] Define the offline grace period.
- [ ] Define the manual machine-reset process.
- [ ] Define which features are entitlements.

### Backend licensing boundary

- [ ] Add pure license status and entitlement models.
- [ ] Add a licensing provider adapter.
- [ ] Add activation, status, refresh, and deactivation services.
- [ ] Add API endpoints for activation, status, refresh, and deactivation.
- [ ] Store only the public verification key in customer software.
- [ ] Keep license-signing and administrative credentials outside customer images.

### Machine identity

- [ ] Read the machine identity from the host, not from a replaceable container ID.
- [ ] Hash or HMAC the stable identifier before transmitting it.
- [ ] Add an installation identifier.
- [ ] Document machine-fingerprint processing in the privacy material.
- [ ] Plan a later native agent backed by TPM, Secure Enclave, or the OS keychain.

### Enforce entitlements

Require an active entitlement for:

- [ ] Media upload and URL import
- [ ] Transcription
- [ ] Editorial analysis
- [ ] Preview rendering
- [ ] Final rendering
- [ ] Publishing

Continue allowing these operations when a license is read-only:

- [ ] Open existing projects
- [ ] View existing clips
- [ ] Download existing exports
- [ ] Back up customer data
- [ ] Deactivate or replace the installation

### Licensing tests

- [ ] The first machine activates successfully.
- [ ] The same license is rejected on a second machine.
- [ ] Deactivation allows a replacement machine.
- [ ] A temporary licensing outage uses the grace period.
- [ ] Grace-period expiration enters read-only mode.
- [ ] Suspension blocks new commercial operations.
- [ ] License failure never deletes customer data.

### Exit gate

- [ ] Copying the Compose file and data volume to another machine does not create a valid
      second installation.
- [ ] A legitimate customer can transfer their license through a documented process.
- [ ] Licensing outages do not immediately interrupt paid customers.

## Milestone 6: Build the installer and updater

**Purpose:** Let a non-developer install and maintain ReachCut without cloning the
repository or using development commands.

### Customer installation package

The initial package should contain only the material needed to operate ReachCut:

```text
reachcut/
├── install
├── update
├── backup
├── restore
├── uninstall
├── compose.customer.yaml
├── release-manifest.json
├── LICENSE.txt
├── THIRD_PARTY_NOTICES.txt
└── README.txt
```

### Installer steps

- [ ] Display the ReachCut version and license agreement.
- [ ] Check the operating system and CPU architecture.
- [ ] Check Docker availability and supported version.
- [ ] Check RAM and available storage.
- [ ] Ask for the license key.
- [ ] Activate the current machine.
- [ ] Obtain short-lived, pull-only registry access.
- [ ] Pull digest-pinned, signed images.
- [ ] Create customer-specific volumes and local secrets.
- [ ] Write the customer configuration.
- [ ] Start the services.
- [ ] Wait for health checks.
- [ ] Open the local web application.
- [ ] Print actionable recovery instructions if any step fails.

### Updater steps

- [ ] Verify the current license.
- [ ] Download and verify the signed release manifest.
- [ ] Create a pre-update backup.
- [ ] Pull the new image digests.
- [ ] Verify image signatures.
- [ ] Stop services safely.
- [ ] Run database migrations.
- [ ] Start the new version.
- [ ] Run application health checks.
- [ ] Roll back images and data if health checks or migrations fail.

### Uninstaller behavior

- [ ] Let the customer choose whether to preserve or remove application data.
- [ ] Deactivate the machine when possible.
- [ ] Remove registry credentials and generated local secrets.
- [ ] Clearly report which files and volumes remain.

### Exit gate

- [ ] A non-developer can install ReachCut on a clean supported machine.
- [ ] Installation does not require the Git repository.
- [ ] Updating preserves existing projects.
- [ ] A failed update returns to the previous working version.
- [ ] Uninstallation does not unexpectedly delete customer data.

## Milestone 7: Add onboarding, diagnostics, and support

**Purpose:** Reduce installation failures and let support diagnose problems without
receiving private customer media.

### First-run onboarding

- [ ] Show license status.
- [ ] Confirm the media and backup locations.
- [ ] Detect the available hardware profile.
- [ ] Recommend a transcription and rendering profile.
- [ ] Download models with visible progress and retry support.
- [ ] Select the default spoken language.
- [ ] Run a test transcription.
- [ ] Run a test render.
- [ ] Configure optional social accounts.
- [ ] Show a final readiness summary.

### Diagnostics page

- [ ] ReachCut and schema version
- [ ] Installation ID and non-secret license status
- [ ] Operating system and hardware profile
- [ ] Free storage
- [ ] API and web health
- [ ] FFmpeg version
- [ ] Installed model status
- [ ] Social-provider readiness
- [ ] Backup status
- [ ] Last job failure and retry guidance

### Sanitized support bundle

- [ ] Include application and container logs with size limits.
- [ ] Include hardware, version, stage, and health information.
- [ ] Exclude media, transcript content, credentials, license keys, registry tokens,
      passwords, encryption keys, and private paths.
- [ ] Add an automated test proving known secret fields are removed.

### Exit gate

- [ ] A new customer completes the first sample export without developer intervention.
- [ ] Common failures have customer-facing recovery instructions.
- [ ] Support can diagnose a failed installation from a sanitized bundle.

## Milestone 8: Prepare the commercial offer and legal material

**Purpose:** Define what the customer is buying and what both parties are responsible for.

This section should be reviewed by appropriate legal and accounting professionals before
a public sale.

### Product offer

- [ ] Name the pilot product and included features.
- [ ] Define the pilot period and price.
- [ ] Define one-machine licensing and transfer rules.
- [ ] Define included installation and support.
- [ ] Define update eligibility.
- [ ] Define cancellation and refund behavior.
- [ ] Define supported hardware and exclusions.

### Required material

- [ ] Commercial EULA or pilot service agreement
- [ ] Privacy policy
- [ ] Acceptable-use policy
- [ ] Media-rights responsibility
- [ ] Refund and cancellation terms
- [ ] Machine-fingerprint disclosure
- [ ] Third-party dependency and asset notices
- [ ] Model-license review
- [ ] FFmpeg distribution review
- [ ] ReachCut name and trademark review
- [ ] Support expectations and response channel

### Pilot administration

- [ ] Create a manual invoice process.
- [ ] Create a manual license-issuance procedure.
- [ ] Create a customer installation record without storing private media information.
- [ ] Create a support-contact process.
- [ ] Create a license reset and machine replacement procedure.

### Exit gate

- [ ] A customer can understand the product, price, support, license, and cancellation
      terms before paying.
- [ ] Required third-party notices ship with the product.
- [ ] The pilot agreement and privacy material have been reviewed appropriately.

## Milestone 9: Produce the first release candidate

**Purpose:** Exercise the entire customer lifecycle on a machine that has never contained
the ReachCut repository.

### Create the release candidate

- [ ] Create tag `v0.1.0-pilot.1`.
- [ ] Publish signed release images.
- [ ] Generate the release manifest.
- [ ] Generate release notes.
- [ ] Generate the customer installation package.
- [ ] Archive the SBOM, scan results, digests, and source revision.

### Clean-machine acceptance test

- [ ] Install Docker prerequisites.
- [ ] Install ReachCut without repository access.
- [ ] Activate the license.
- [ ] Complete first-run onboarding.
- [ ] Upload authorized media.
- [ ] Transcribe and analyze it.
- [ ] Review and edit a proposed clip.
- [ ] Render a preview.
- [ ] Render a final export.
- [ ] Restart the computer and continue using the project.
- [ ] Create a backup.
- [ ] Upgrade to a test patch release.
- [ ] Roll back deliberately.
- [ ] Restore the backup on a clean installation.
- [ ] Test offline grace behavior.
- [ ] Test license expiration and read-only behavior.
- [ ] Deactivate and transfer the license.
- [ ] Uninstall while preserving data.
- [ ] Uninstall while deliberately removing data.

### Exit gate

- [ ] No release-blocking defect remains.
- [ ] Every failed step produces actionable guidance.
- [ ] Backup, update, rollback, and restore have been demonstrated.
- [ ] The installation package contains no repository or production secrets.

## Milestone 10: Run the paid pilot

**Purpose:** Determine whether customers receive enough repeated value to justify a
broader release.

### Onboard each pilot customer

- [ ] Confirm the customer has supported hardware.
- [ ] Sign the pilot agreement.
- [ ] Issue the invoice.
- [ ] Create one customer license.
- [ ] Install ReachCut together.
- [ ] Process the customer's first authorized video.
- [ ] Confirm the customer can create a second project without assistance.
- [ ] Schedule a weekly feedback session during the pilot.

### Measure pilot results

Track these values for each customer:

- Installation duration
- Time to first successful export
- Processing success and failure rate
- Number and percentage of accepted clips
- Time saved compared with the previous workflow
- Projects processed per week
- Support minutes per customer
- Number of license resets or failed updates
- Weekly return usage
- Willingness to continue paying

### Pilot decision

After three to five customers complete the pilot, decide whether to:

- [ ] Continue improving private local installations.
- [ ] Introduce multi-machine agency plans.
- [ ] Add a hosted OAuth broker.
- [ ] Add automated subscription billing.
- [ ] Begin a self-service public release.
- [ ] Stop or reposition the product based on evidence.

## Public-release gates

Do not begin a general public launch until all applicable statements are true:

- [ ] At least three pilot customers use ReachCut repeatedly.
- [ ] Customers demonstrate willingness to continue paying.
- [ ] Clean-machine installation succeeds reliably.
- [ ] Updates and rollback are proven.
- [ ] Backup and restore are proven.
- [ ] One-machine licensing works without frequent false rejections.
- [ ] Customer data remains available after license expiration.
- [ ] Critical and high-risk security findings are resolved or formally accepted.
- [ ] Social-platform production approvals are sufficient for the advertised features.
- [ ] Legal and third-party license reviews are complete.
- [ ] Support demand is sustainable.
- [ ] The supported-platform and hardware documentation is accurate.

## Proposed execution schedule

This is an initial estimate for one developer. Adjust it using evidence from each
milestone.

| Week | Primary outcome                                                        |
| ---- | ---------------------------------------------------------------------- |
| 1    | Confirm platform, hardware, licensing, and pilot scope                 |
| 2    | Activate CircleCI and publish the first internal private images        |
| 3    | Build commercial images and complete the Python compilation experiment |
| 4    | Add migrations, backup, restore, and upgrade tests                     |
| 5    | Add machine activation and entitlement enforcement                     |
| 6    | Build the first customer installer and updater                         |
| 7    | Add onboarding, diagnostics, and support bundles                       |
| 8    | Complete legal preparation and the internal release candidate          |
| 9–12 | Run three to five paid pilots and fix repeated blockers                |

## Immediate next actions

Complete these actions before starting any later milestone:

1. [x] Commit and push `.circleci/config.yml` and `docs/circleci.md`.
2. [ ] Connect the private repository to CircleCI.
3. [ ] Confirm all three CircleCI jobs succeed on `main`.
4. [ ] Protect `main` using the successful CircleCI validation check.
5. [ ] Select the first supported customer operating system.
6. [ ] Confirm whether the first release must work offline.
7. [ ] Create the private container registry namespace.
8. [ ] Design the restricted CircleCI release context.
9. [ ] Implement the tag-triggered internal release workflow.
10. [ ] Publish and test `v0.1.0-internal.1` before building customer licensing.

## Decision log

Record decisions that materially affect customers, security, compatibility, pricing, or
operations.

| Date       | Decision                             | Reason                                               | Consequences                                         | Owner |
| ---------- | ------------------------------------ | ---------------------------------------------------- | ---------------------------------------------------- | ----- |
| YYYY-MM-DD | Example: Support Ubuntu x86-64 first | First pilot customers use managed Linux workstations | Windows and macOS are unsupported in the first pilot | Name  |

## Release record

Create one row for every internal, pilot, or stable release.

| Version             | Date    | Source revision | API digest | Web digest | Migration tested | Clean install tested | Released to   |
| ------------------- | ------- | --------------- | ---------- | ---------- | ---------------- | -------------------- | ------------- |
| `v0.1.0-internal.1` | Pending | Pending         | Pending    | Pending    | No               | No                   | Internal only |

## Explicitly deferred work

The private pilot does not require these capabilities unless customer evidence changes the
decision:

- Multi-tenant SaaS architecture
- Central customer media storage
- Cloud GPU orchestration
- PostgreSQL migration
- Enterprise SSO
- Complex team roles
- Permanent free plan
- Automated tax and subscription billing
- Mobile applications
- Large template or asset marketplaces

Deferring these items protects time for installation reliability, data safety, licensing,
and customer validation.
