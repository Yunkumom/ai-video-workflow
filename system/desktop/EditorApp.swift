import Darwin
import AppKit
import WebKit

final class EditorApp: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var process: Process?
    var configuration = [String: String]()
    var connection = [String: String]()
    var stopping = false
    var readyData = Data()
    var verificationAttempts = 0
    var terminationPending = false
    var verificationRestarted = false
    var startupPanel: NSStackView!
    func trace(_ stage: String) {
        NSLog("Video editor: %@", stage)
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let data = try Data(contentsOf: Bundle.main.url(forResource: "project", withExtension: "json")!)
            configuration = try JSONDecoder().decode([String: String].self, from: data)
            let config = WKWebViewConfiguration(); config.websiteDataStore = .nonPersistent()
            config.mediaTypesRequiringUserActionForPlayback = []
            if CommandLine.arguments.contains("--verify-ui") {
                config.userContentController.addUserScript(WKUserScript(source: "window.__testing=true", injectionTime: .atDocumentStart, forMainFrameOnly: true))
            }
            config.userContentController.add(self, name: "desktop")
            web = WKWebView(frame: .zero, configuration: config); web.navigationDelegate = self; web.uiDelegate = self
            window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1400, height: 900), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            window.title = "影片編輯器 · " + (configuration["project"] ?? "")
            let content = NSView(frame: window.contentView!.bounds)
            web.frame = content.bounds; web.autoresizingMask = [.width, .height]; content.addSubview(web)
            startupPanel = NSStackView(); startupPanel.orientation = .vertical; startupPanel.spacing = 16
            startupPanel.addArrangedSubview(NSTextField(labelWithString: "正在開啟影片編輯器…"))
            let explanation = NSTextField(wrappingLabelWithString: "首次開啟時，macOS 可能要求資料夾存取權。若一直停在這裡，請選取專案工作流程資料夾。")
            explanation.preferredMaxLayoutWidth = 440; startupPanel.addArrangedSubview(explanation)
            startupPanel.addArrangedSubview(NSButton(title: "選取工作流程資料夾", target: self, action: #selector(chooseAccessFolder)))
            content.addSubview(startupPanel); startupPanel.translatesAutoresizingMaskIntoConstraints = false
            NSLayoutConstraint.activate([startupPanel.centerXAnchor.constraint(equalTo: content.centerXAnchor), startupPanel.centerYAnchor.constraint(equalTo: content.centerYAnchor), startupPanel.widthAnchor.constraint(equalToConstant: 440)])
            window.contentView = content; window.center(); window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            let menu = NSMenu(); let appMenu = NSMenuItem(); menu.addItem(appMenu); appMenu.submenu = NSMenu()
            appMenu.submenu?.addItem(withTitle: "結束編輯器", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
            let edit = NSMenuItem(); edit.title = "編輯"; edit.submenu = NSMenu(title: "編輯"); menu.addItem(edit)
            for (title, action, key) in [("剪下", "cut:", "x"), ("複製", "copy:", "c"), ("貼上", "paste:", "v"), ("全選", "selectAll:", "a")] { edit.submenu?.addItem(withTitle: title, action: Selector(action), keyEquivalent: key) }
            NSApp.mainMenu = menu
            if configuration["project", default: ""].isEmpty { chooseInitialProject() } else { start() }
        } catch { alert(error.localizedDescription) }
    }
    func chooseInitialProject() {
        guard let root = configuration["root"] else { return }
        let choice = NSAlert(); choice.messageText = "影片編輯器 · 選擇專案"
        choice.informativeText = "開啟既有專案，或建立新的空白剪輯專案。"
        choice.addButton(withTitle: "開啟專案"); choice.addButton(withTitle: "建立新專案")
        let recent = UserDefaults.standard.string(forKey: "recentProject:" + root)
        if recent != nil { choice.addButton(withTitle: "最近專案：" + recent!) }
        choice.addButton(withTitle: "取消")
        let answer = choice.runModal().rawValue - NSApplication.ModalResponse.alertFirstButtonReturn.rawValue
        var project: String?
        if answer == 0 {
            let picker = NSOpenPanel(); picker.canChooseFiles = false; picker.canChooseDirectories = true
            picker.directoryURL = URL(fileURLWithPath: root + "/3_output"); picker.message = "選取 1_input 或 3_output 下的專案資料夾"
            if picker.runModal() == .OK, let url = picker.url {
                let parent = url.deletingLastPathComponent().resolvingSymlinksInPath().path
                if ["1_input", "3_output"].map({ URL(fileURLWithPath: root).appendingPathComponent($0).resolvingSymlinksInPath().path }).contains(parent) { project = url.lastPathComponent }
                else { alert("請選擇工作流程內的專案資料夾。") }
            }
        } else if answer == 1 {
            let create = NSAlert(); create.messageText = "新專案名稱"; create.informativeText = "使用英文、中文、數字、底線或連字號。"
            let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 26)); create.accessoryView = field
            create.addButton(withTitle: "建立"); create.addButton(withTitle: "取消")
            if create.runModal() == .alertFirstButtonReturn {
                let value = field.stringValue
                if FileManager.default.fileExists(atPath: root + "/3_output/" + value) || FileManager.default.fileExists(atPath: root + "/1_input/" + value) { alert("此專案已存在，請使用開啟專案。") }
                else { project = value }
            }
        } else if answer == 2, let recent = recent { project = recent }
        guard let project = project, project.range(of: "^[\\w-]{1,80}$", options: .regularExpression) != nil else { NSApp.terminate(nil); return }
        configuration["project"] = project; start()
    }
    func alert(_ message: String) { let a = NSAlert(); a.messageText = message; a.runModal() }
    @objc func chooseAccessFolder() {
        guard let root = configuration["root"] else { return }
        let picker = NSOpenPanel(); picker.canChooseFiles = false; picker.canChooseDirectories = true
        picker.directoryURL = URL(fileURLWithPath: root, isDirectory: true); picker.prompt = "開啟此資料夾"
        picker.beginSheetModal(for: window) { [weak self] result in
            guard result == .OK, let self = self, let url = picker.url else { return }
            guard url.standardizedFileURL.path == root else { self.alert("請選擇 ai-video-workflow 資料夾。"); return }
            _ = url.startAccessingSecurityScopedResource()
            self.stopping = true; self.process?.terminate(); self.process?.waitUntilExit()
            self.stopping = false; self.start()
        }
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = message; a.addButton(withTitle: "確定"); a.addButton(withTitle: "取消")
        a.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let picker = NSOpenPanel(); picker.allowsMultipleSelection = parameters.allowsMultipleSelection; picker.canChooseDirectories = false
        picker.beginSheetModal(for: window) { completionHandler($0 == .OK ? picker.urls : nil) }
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        trace("web navigation finished")
        startupPanel.isHidden = true
        if CommandLine.arguments.contains("--verify-ui") { verifyUI() }
    }
    func verifyUI() {
        verificationAttempts += 1
        web.evaluateJavaScript("typeof doc !== 'undefined' && !!doc && Object.keys(layouts).length === doc.cues.length") { [weak self] ready, error in
            guard let self = self else { return }
            if ready as? Bool != true && self.verificationAttempts < 90 { DispatchQueue.main.asyncAfter(deadline: .now()+1) { self.verifyUI() }; return }
            guard let root = self.configuration["root"], let project = self.configuration["project"] else { return }
            let folder = URL(fileURLWithPath: root+"/2_processing/"+project+"/desktop-editor")
            let script = (try? String(contentsOfFile: root+"/system/tests/editor_desktop_browser.js", encoding: .utf8)) ?? "({error:'missing test'})"
            self.web.evaluateJavaScript(script) { result, error in
                let value = result ?? ["error": error?.localizedDescription ?? "not ready"]
                if let data = try? JSONSerialization.data(withJSONObject: value, options: .prettyPrinted) { try? data.write(to: folder.appendingPathComponent("wkwebview-check.json")) }
                self.web.takeSnapshot(with: nil) { image, _ in
                    if let data = image?.tiffRepresentation, let bitmap = NSBitmapImageRep(data: data), let png = bitmap.representation(using: .png, properties: [:]) { try? png.write(to: folder.appendingPathComponent("wkwebview-check.png")) }
                }
                self.web.evaluateJavaScript("native('import')")
            }
        }
    }
    func start() {
        trace("starting controller")
        readyData = Data()
        guard let root = configuration["root"], let python = configuration["python"], let project = configuration["project"] else { alert("App 設定不完整。"); return }
        let lockPath = root + "/2_processing/" + project + "/desktop-editor/controller.lock"
        let descriptor = Darwin.open(lockPath, O_RDWR)
        if descriptor >= 0 {
            if flock(descriptor, LOCK_EX | LOCK_NB) != 0 { Darwin.close(descriptor); alert("這個專案已有編輯器開啟，請回到原本視窗。"); return }
            flock(descriptor, LOCK_UN); Darwin.close(descriptor)
        }
        UserDefaults.standard.set(project, forKey: "recentProject:" + root)
        window.title = "影片編輯器 · " + project
        let p = Process(); p.executableURL = URL(fileURLWithPath: python)
        // Finder launches must not depend on Python resolving a Desktop cwd.
        p.currentDirectoryURL = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
        p.arguments = ["-P", "-m", "system.desktop_server", "--root", root, "--project", project]
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"; env["PYTHONPATH"] = root; p.environment = env
        let pipe = Pipe(); p.standardOutput = pipe; let errors = Pipe(); p.standardError = errors
        errors.fileHandleForReading.readabilityHandler = { [weak self] h in
            let data = h.availableData
            if !data.isEmpty { DispatchQueue.main.async { self?.web.evaluateJavaScript("window.desktopError?.('本機控制器發生錯誤，工作已保留。')") } }
        }
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let data = h.availableData
            DispatchQueue.main.async {
                guard let self = self, !data.isEmpty else { return }
                self.readyData.append(data)
                if let newline = self.readyData.firstIndex(of: 10), let result = try? JSONDecoder().decode([String:String].self, from: self.readyData.prefix(upTo: newline)), let url = result["url"], let token = result["token"] {
                    pipe.fileHandleForReading.readabilityHandler = nil; self.connection = result
                    self.trace("controller ready")
                    var request = URLRequest(url: URL(string: url)!); request.setValue(token, forHTTPHeaderField: "X-Workflow-Token")
                    self.web.load(request)
                }
            }
        }
        p.terminationHandler = { [weak self] _ in DispatchQueue.main.async {
            guard let self = self, !self.stopping else { return }
            self.web.evaluateJavaScript("typeof doc !== 'undefined' && doc ? JSON.stringify(doc) : null") { value, _ in
                if let text = value as? String, let root = self.configuration["root"], let project = self.configuration["project"], !CommandLine.arguments.contains("--verify-ui") {
                    try? text.write(toFile: root+"/3_output/"+project+"/保存區/工作中/recovery-pending.json", atomically: true, encoding: .utf8)
                }
                if !CommandLine.arguments.contains("--verify-ui") { self.alert("本機控制器已停止；已保留工作。按確定重新開啟。") }
                self.start()
            }
        } }
        process = p
        do { try p.run(); trace("controller process launched") } catch { alert("無法啟動 Python：" + error.localizedDescription) }
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, message.frameInfo.request.url?.host == "127.0.0.1", let body = message.body as? [String:String], let action = body["action"] else { return }
        if action == "fullscreen" { window.toggleFullScreen(nil); return }
        if action == "project" {
            let picker = NSOpenPanel(); picker.canChooseFiles = false; picker.canChooseDirectories = true
            picker.message = "選擇 1_input 或 3_output 下的專案資料夾"
            picker.beginSheetModal(for: window) { [weak self] result in
                guard result == .OK, let self = self, let url = picker.url, let root = self.configuration["root"] else { return }
                let parent = url.deletingLastPathComponent().standardizedFileURL.path
                if ![root+"/1_input", root+"/3_output"].contains(parent) { self.alert("請選擇工作流程內的專案資料夾。"); return }
                self.stopping = true; self.process?.terminate(); self.process?.waitUntilExit()
                self.configuration["project"] = url.lastPathComponent; self.stopping = false; self.start()
            }; return
        }
        if action == "saveCopy" {
            web.evaluateJavaScript("JSON.stringify(doc,null,2)") { [weak self] value, _ in
                guard let self = self, let text = value as? String else { return }
                let picker = NSSavePanel(); picker.nameFieldStringValue = "project.video-editor.json"
                picker.beginSheetModal(for: self.window) { result in
                    if result == .OK, let url = picker.url { do { try text.write(to: url, atomically: true, encoding: .utf8) } catch { self.alert(error.localizedDescription) } }
                }
            }; return
        }
        if action == "reveal", let root = configuration["root"], let project = configuration["project"] { NSWorkspace.shared.open(URL(fileURLWithPath: root+"/3_output/"+project)); return }
        if action != "import" { return }
        let picker = NSOpenPanel(); picker.canChooseDirectories = false; picker.allowsMultipleSelection = true
        if CommandLine.arguments.contains("--verify-ui"), let root = configuration["root"], let project = configuration["project"] {
            DispatchQueue.main.asyncAfter(deadline: .now()+0.5) {
                let data = try? JSONSerialization.data(withJSONObject: ["nativePickerVisible": picker.isVisible, "multipleSelection": picker.allowsMultipleSelection])
                try? data?.write(to: URL(fileURLWithPath: root+"/2_processing/"+project+"/desktop-editor/native-picker-check.json"))
                picker.cancel(nil)
                if !self.verificationRestarted {
                    self.verificationRestarted = true
                    try? Data("{\"controllerRestartRequested\":true}".utf8).write(to: URL(fileURLWithPath: root+"/2_processing/"+project+"/desktop-editor/native-recovery-check.json"))
                    DispatchQueue.main.asyncAfter(deadline: .now()+0.5) { self.process?.terminate() }
                } else {
                    try? Data("{\"controllerRestartRequested\":true,\"reopenedAndVerified\":true}".utf8).write(to: URL(fileURLWithPath: root+"/2_processing/"+project+"/desktop-editor/native-recovery-check.json"))
                }
            }
        }
        picker.beginSheetModal(for: window) { [weak self] result in
            guard result == .OK, let self = self, let url = self.connection["url"] else { return }
            var request = URLRequest(url: URL(string: url+"native/import")!); request.httpMethod = "POST"
            request.setValue(self.connection["token"], forHTTPHeaderField: "X-Workflow-Token")
            request.setValue(self.connection["native"], forHTTPHeaderField: "X-Native-Token")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: ["paths": picker.urls.map { $0.path }])
            URLSession.shared.dataTask(with: request) { data, _, error in
                DispatchQueue.main.async {
                    if let data = data, let json = String(data: data, encoding: .utf8) { self.web.evaluateJavaScript("window.imported(\(json))") }
                    else { self.alert(error?.localizedDescription ?? "匯入失敗。") }
                }
            }.resume()
        }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let allowed = navigationAction.request.url?.absoluteString.hasPrefix(connection["url"] ?? "invalid:") ?? false
        decisionHandler(allowed ? .allow : .cancel)
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if stopping { return .terminateNow }
        if terminationPending { return .terminateLater }
        terminationPending = true
        web.callAsyncJavaScript("if (!window.__testing) await save(); return (await api('jobs')).some(j=>j.status==='running');", arguments: [:], in: nil, in: .page) { [weak self] result in
            guard let self = self else { sender.reply(toApplicationShouldTerminate: true); return }
            self.terminationPending = false
            if case .success(let value) = result, value as? Bool == true {
                self.window.makeKeyAndOrderFront(nil); self.alert("影片或辨識正在處理，完成後再關閉編輯器。")
                sender.reply(toApplicationShouldTerminate: false)
            } else { self.stopping = true; sender.reply(toApplicationShouldTerminate: true) }
        }
        return .terminateLater
    }
    func applicationWillTerminate(_ notification: Notification) { stopping = true; process?.terminate() }
}
let app = NSApplication.shared
let delegate = EditorApp(); app.delegate = delegate
app.setActivationPolicy(.regular); app.run()
