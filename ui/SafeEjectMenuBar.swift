import Cocoa
import Foundation
import WebKit

// MARK: - Custom Borderless Floating Panel
// Provides 100% transparent container with no native NSPopover frame, no arrow, and no halo.
class CustomCardPanel: NSPanel {
    override var canBecomeKey: Bool { return true }
    override var canBecomeMain: Bool { return true }
}

// MARK: - SafeEject Custom Menu Bar App with Card UI
class SafeEjectStatusItemManager: NSObject, WKScriptMessageHandler, NSWindowDelegate, WKUIDelegate {
    var statusItem: NSStatusItem!
    var panel: CustomCardPanel!
    var webView: WKWebView!
    var pythonPath = "/usr/bin/python3"
    var scriptPath = ""
    var htmlCardPath = ""
    var globalClickMonitor: Any?
    var livePollingTimer: Timer?
    var isSyncingState = false

    override init() {
        super.init()
        locatePaths()
        setupPanel()
        setupStatusItem()
    }

    func locatePaths() {
        var potentialRoots: [String] = []

        // 1. Environment variable override
        if let envRoot = ProcessInfo.processInfo.environment["SAFEEJECT_PROJECT_DIR"], !envRoot.isEmpty {
            potentialRoots.append(envRoot)
        }

        // 2. Current working directory
        let cwd = FileManager.default.currentDirectoryPath
        potentialRoots.append(cwd)

        // 3. Executable path and ancestor directories
        let execPath = CommandLine.arguments.first ?? Bundle.main.executablePath ?? ""
        if !execPath.isEmpty {
            let execURL = URL(fileURLWithPath: execPath).resolvingSymlinksInPath()
            let execDir = execURL.deletingLastPathComponent().path
            potentialRoots.append(execDir)
            let parentDir = execURL.deletingLastPathComponent().deletingLastPathComponent().path
            potentialRoots.append(parentDir)
            let grandparentDir = execURL.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().path
            potentialRoots.append(grandparentDir)
        }

        // 4. Bundle path and parent directories
        let bundlePath = Bundle.main.bundlePath
        let bundleURL = URL(fileURLWithPath: bundlePath).resolvingSymlinksInPath()
        potentialRoots.append(bundleURL.path)
        potentialRoots.append(bundleURL.deletingLastPathComponent().path)

        // Find root where main.py exists
        var foundRoot: String?
        for candidate in potentialRoots {
            let testMain = (candidate as NSString).appendingPathComponent("main.py")
            if FileManager.default.fileExists(atPath: testMain) {
                foundRoot = candidate
                scriptPath = testMain
                break
            }
        }

        // Locate SafeDriveEjectorCard.html
        var htmlCandidates: [String] = []
        if let root = foundRoot {
            htmlCandidates.append((root as NSString).appendingPathComponent("ui/components/SafeDriveEjectorCard.html"))
        }
        for candidate in potentialRoots {
            htmlCandidates.append((candidate as NSString).appendingPathComponent("ui/components/SafeDriveEjectorCard.html"))
            htmlCandidates.append((candidate as NSString).appendingPathComponent("SafeDriveEjectorCard.html"))
            if let resPath = Bundle.main.resourcePath {
                htmlCandidates.append((resPath as NSString).appendingPathComponent("SafeDriveEjectorCard.html"))
                htmlCandidates.append((resPath as NSString).appendingPathComponent("ui/components/SafeDriveEjectorCard.html"))
            }
        }

        for path in htmlCandidates {
            if FileManager.default.fileExists(atPath: path) {
                htmlCardPath = path
                break
            }
        }

        // Detect python3 executable
        var pythonCandidates: [String] = []
        if let root = foundRoot {
            pythonCandidates.append((root as NSString).appendingPathComponent(".venv/bin/python3"))
            pythonCandidates.append((root as NSString).appendingPathComponent("venv/bin/python3"))
        }
        pythonCandidates.append("/opt/homebrew/bin/python3")
        pythonCandidates.append("/usr/local/bin/python3")
        pythonCandidates.append("/usr/bin/python3")

        for path in pythonCandidates {
            if FileManager.default.fileExists(atPath: path) {
                pythonPath = path
                break
            }
        }
    }

    func setupPanel() {
        let initialSize = NSSize(width: 192, height: 316)
        panel = CustomCardPanel(
            contentRect: NSRect(origin: .zero, size: initialSize),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.level = .statusBar
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.delegate = self

        // Configure WKWebView with script bridge
        let config = WKWebViewConfiguration()
        let userContent = WKUserContentController()
        userContent.add(self, name: "safeEjectBridge")
        config.userContentController = userContent
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")

        webView = WKWebView(frame: NSRect(origin: .zero, size: initialSize), configuration: config)
        webView.uiDelegate = self
        webView.setValue(false, forKey: "drawsBackground") // 100% transparent background
        if #available(macOS 12.0, *) {
            webView.underPageBackgroundColor = .clear
        }
        webView.wantsLayer = true
        webView.layer?.backgroundColor = NSColor.clear.cgColor
        webView.autoresizingMask = [.width, .height]

        panel.contentView = webView
        panel.contentView?.wantsLayer = true
        panel.contentView?.layer?.backgroundColor = NSColor.clear.cgColor
        loadCardHTML()
    }

    func loadCardHTML() {
        guard !htmlCardPath.isEmpty else { return }
        let fileURL = URL(fileURLWithPath: htmlCardPath)
        let directoryURL = fileURL.deletingLastPathComponent()
        webView.loadFileURL(fileURL, allowingReadAccessTo: directoryURL)
    }

    func setupStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.image = createDiamondToggleIcon(isActive: false)
            button.imagePosition = .imageOnly
            button.action = #selector(togglePanel(_:))
            button.target = self
            button.toolTip = "Safe Drive Ejector Tool"
        }
    }

    // Creates the diamond toggle icon (Red 45deg when closed, Green 135deg when open)
    private func createDiamondToggleIcon(isActive: Bool = false) -> NSImage {
        let size = NSSize(width: 22, height: 22)
        let img = NSImage(size: size)
        img.lockFocus()

        let context = NSGraphicsContext.current?.cgContext

        // Outer rotated diamond
        context?.saveGState()
        context?.translateBy(x: 11, y: 11)
        let rotationAngle = isActive ? (CGFloat.pi * 3.0 / 4.0) : (CGFloat.pi / 4.0)
        context?.rotate(by: rotationAngle)

        let diamondRect = CGRect(x: -7, y: -7, width: 14, height: 14)
        let diamondPath = NSBezierPath(roundedRect: diamondRect, xRadius: 1.5, yRadius: 1.5)
        let strokeColor = isActive ? NSColor(red: 100/255, green: 253/255, blue: 31/255, alpha: 1.0) : NSColor(red: 255/255, green: 51/255, blue: 51/255, alpha: 1.0)
        strokeColor.setStroke()
        diamondPath.lineWidth = 1.5
        diamondPath.stroke()

        // Three hamburger lines inside (rotated back)
        context?.rotate(by: -rotationAngle)

        let line1 = NSBezierPath(rect: NSRect(x: -5, y: 3, width: 10, height: 1.5))
        let line2 = NSBezierPath(rect: NSRect(x: -5, y: -0.75, width: 10, height: 1.5))
        let line3 = NSBezierPath(rect: NSRect(x: -5, y: -4.5, width: 10, height: 1.5))

        NSColor.white.setFill()
        line1.fill()
        line2.fill()
        line3.fill()

        context?.restoreGState()

        img.unlockFocus()
        img.isTemplate = false
        return img
    }

    @objc func togglePanel(_ sender: AnyObject?) {
        if panel.isVisible && panel.alphaValue > 0.0 {
            closePanel()
        } else {
            showPanel()
        }
    }

    func showPanel() {
        guard let button = statusItem.button else { return }
        if webView.url == nil {
            loadCardHTML()
        }
        positionPanel()
        panel.alphaValue = 0.0
        panel.makeKeyAndOrderFront(nil)
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.12
            panel.animator().alphaValue = 1.0
        }
        button.image = createDiamondToggleIcon(isActive: true)

        // Start real-time drive status polling while panel is visible
        startLivePolling()

        // Close panel when user clicks outside
        if globalClickMonitor == nil {
            globalClickMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
                guard let self = self, self.panel.isVisible else { return }
                if let button = self.statusItem.button, let window = button.window {
                    let mouseLoc = NSEvent.mouseLocation
                    let buttonFrame = window.convertToScreen(button.convert(button.bounds, to: nil))
                    if buttonFrame.contains(mouseLoc) {
                        return // Handled by status button toggle
                    }
                }
                DispatchQueue.main.async {
                    self.closePanel()
                }
            }
        }
    }

    func closePanel() {
        guard panel.isVisible else { return }
        stopLivePolling()
        if let monitor = globalClickMonitor {
            NSEvent.removeMonitor(monitor)
            globalClickMonitor = nil
        }
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.12
            panel.animator().alphaValue = 0.0
        }, completionHandler: { [weak self] in
            self?.panel.orderOut(nil)
            self?.statusItem.button?.image = self?.createDiamondToggleIcon(isActive: false)
        })
    }

    func startLivePolling() {
        stopLivePolling()
        syncRealDriveState()
        livePollingTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            guard let self = self, self.panel.isVisible else { return }
            self.syncRealDriveState()
        }
        if let timer = livePollingTimer {
            RunLoop.main.add(timer, forMode: .common)
        }
    }

    func stopLivePolling() {
        livePollingTimer?.invalidate()
        livePollingTimer = nil
    }

    func windowDidResignKey(_ notification: Notification) {
        closePanel()
    }

    func positionPanel() {
        guard let button = statusItem.button, let window = button.window else { return }
        let buttonRectOnScreen = window.convertToScreen(button.convert(button.bounds, to: nil))
        let panelSize = panel.frame.size

        var x = buttonRectOnScreen.midX - (panelSize.width / 2.0)
        var y = buttonRectOnScreen.minY - panelSize.height - 4

        if let screen = window.screen ?? NSScreen.main {
            let screenFrame = screen.visibleFrame
            if x < screenFrame.minX + 4 {
                x = screenFrame.minX + 4
            } else if x + panelSize.width > screenFrame.maxX - 4 {
                x = screenFrame.maxX - panelSize.width - 4
            }
            if y < screenFrame.minY + 4 {
                y = screenFrame.minY + 4
            }
        }

        panel.setFrameOrigin(NSPoint(x: x, y: y))
    }

    func syncRealDriveState() {
        if isSyncingState { return }
        isSyncingState = true
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            defer { self?.isSyncingState = false }
            guard let self = self else { return }
            let statusObj = self.queryStatusJSON()
            guard !statusObj.isEmpty else { return }
            if let jsonData = try? JSONSerialization.data(withJSONObject: statusObj),
               let jsonString = String(data: jsonData, encoding: .utf8) {
                DispatchQueue.main.async {
                    guard self.panel.isVisible else { return }
                    let js = "if(window.updateUIState){ window.updateUIState(\(jsonString)); }"
                    self.webView.evaluateJavaScript(js, completionHandler: nil)
                }
            }
        }
    }

    private func getFloat(_ val: Any?) -> CGFloat? {
        if let v = val as? CGFloat { return v }
        if let v = val as? Double { return CGFloat(v) }
        if let v = val as? Int { return CGFloat(v) }
        if let v = val as? NSNumber { return CGFloat(v.doubleValue) }
        return nil
    }

    // MARK: - WKScriptMessageHandler (IPC from SafeDriveEjectorCard.html)
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "safeEjectBridge", let body = message.body as? [String: Any] else { return }

        let action = body["action"] as? String ?? ""

        switch action {
        case "mount":
            let target = body["target"] as? String ?? (body["driverId"] != nil ? "\(body["driverId"]!)" : "all")
            let drivers = body["drivers"] as? [String] ?? []
            if (target == "all" || target == "checked") && !drivers.isEmpty {
                runCLICommand(["remount"] + drivers)
            } else if target == "all" {
                runCLICommand(["remount-all"])
            } else {
                runCLICommand(["remount", target])
            }
        case "unmount":
            let target = body["target"] as? String ?? (body["driverId"] != nil ? "\(body["driverId"]!)" : "all")
            let drivers = body["drivers"] as? [String] ?? []
            if (target == "all" || target == "checked") && !drivers.isEmpty {
                runCLICommand(["eject"] + drivers)
            } else if target == "all" {
                runCLICommand(["eject-now"])
            } else {
                runCLICommand(["eject", target])
            }
        case "ejectNow":
            let drivers = body["drivers"] as? [String] ?? []
            if !drivers.isEmpty {
                runCLICommand(["eject-now"] + drivers)
            } else {
                runCLICommand(["eject-now"])
            }
        case "resizePopover":
            if let w = getFloat(body["width"]), let h = getFloat(body["height"]) {
                DispatchQueue.main.async {
                    let screenHeight = NSScreen.main?.visibleFrame.height ?? 800
                    let maxHeight = max(316, screenHeight - 60)
                    let finalH = min(h, maxHeight)
                    let newSize = NSSize(width: w, height: finalH)

                    if self.panel.isVisible {
                        var frame = self.panel.frame
                        let deltaH = finalH - frame.height
                        let deltaW = w - frame.width
                        frame.origin.y -= deltaH
                        frame.origin.x -= deltaW / 2.0
                        frame.size = newSize
                        self.panel.setFrame(frame, display: true, animate: true)
                    } else {
                        self.panel.setContentSize(newSize)
                    }
                }
            }
        case "timer":
            if let preset = body["preset"] as? String {
                runCLICommand(["timer", preset])
            }
        case "openURL":
            if let urlStr = body["url"] as? String, let url = URL(string: urlStr) {
                NSWorkspace.shared.open(url)
            }
        case "quit":
            NSApplication.shared.terminate(self)
        default:
            break
        }
    }

    // MARK: - WKUIDelegate (Opens external links in macOS default browser)
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url {
            NSWorkspace.shared.open(url)
        }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = "Safe Drive Ejector Tool"
        alert.informativeText = message
        alert.addButton(withTitle: "OK")
        alert.runModal()
        completionHandler()
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = "Safe Drive Ejector Tool"
        alert.informativeText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        let response = alert.runModal()
        completionHandler(response == .alertFirstButtonReturn)
    }

    func queryStatusJSON() -> [String: Any] {
        guard !scriptPath.isEmpty else { return [:] }
        let task = Process()
        task.launchPath = pythonPath
        task.arguments = [scriptPath, "json-status"]

        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = Pipe()

        do {
            try task.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            task.waitUntilExit()

            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                return json
            }
        } catch {}
        return [:]
    }

    func runCLICommand(_ args: [String]) {
        guard !scriptPath.isEmpty else { return }
        DispatchQueue.global(qos: .userInitiated).async {
            let task = Process()
            task.launchPath = self.pythonPath
            task.arguments = [self.scriptPath] + args
            try? task.run()
            task.waitUntilExit()
            let success = (task.terminationStatus == 0)
            let cmd = args.first ?? ""
            DispatchQueue.main.async {
                self.syncRealDriveState()
                let js = "if(window.onOperationComplete){ window.onOperationComplete('\(cmd)', \(success)); }"
                self.webView.evaluateJavaScript(js, completionHandler: nil)
            }
        }
    }
}

// Application entry point
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let manager = SafeEjectStatusItemManager()
app.run()
