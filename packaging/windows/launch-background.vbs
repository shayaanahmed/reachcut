Option Explicit

Dim fileSystem, shell, root, nodePath, agentPath, command
Set fileSystem = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fileSystem.GetParentFolderName(WScript.ScriptFullName)
nodePath = root & "\runtime\node.exe"
agentPath = root & "\scripts\reachcut-agent.mjs"
command = Quote(nodePath) & " " & Quote(agentPath) & " --production --no-browser"
shell.Run command, 0, False

Function Quote(value)
  Quote = Chr(34) & value & Chr(34)
End Function
