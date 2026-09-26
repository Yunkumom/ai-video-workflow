import AppKit
import Foundation

struct Style: Decodable { let chinese: String; let english: String; let size: Double; let outline: Double; let color: String }
struct Run: Decodable { let text: String; let scale: Double; let color: String?; let animation: String; let font: String? }
struct Cue: Decodable { let id: String; let text: String; let start: Double; let end: Double; let size: Double; let runs: [Run]; let x: Double; let y: Double; let anchor: String; let boxWidth: Double }
struct Document: Decodable { let style: Style; let cues: [Cue]; let width: Int; let height: Int }
func fail(_ text: String) -> NSError { NSError(domain: "Typography", code: 1, userInfo: [NSLocalizedDescriptionKey: text]) }
func color(_ hex: String) -> NSColor {
    let n = Int(hex.dropFirst(), radix: 16) ?? 0xffffff
    return NSColor(calibratedRed: CGFloat((n >> 16) & 255)/255, green: CGFloat((n >> 8) & 255)/255, blue: CGFloat(n & 255)/255, alpha: 1)
}
func fonts() -> [[String: Any]] {
    NSFontManager.shared.availableFontFamilies.sorted().flatMap { family in
        (NSFontManager.shared.availableMembers(ofFontFamily: family) ?? []).compactMap { member -> [String: Any]? in
            guard let name = member[0] as? String, let weight = member[2] as? Int, let font = NSFont(name: name, size: 16) else { return nil }
            let traits = NSFontManager.shared.traits(of: font)
            if traits.contains(.italicFontMask) || traits.contains(.condensedFontMask) || traits.contains(.expandedFontMask) { return nil }
            return ["family": family, "name": name, "face": member[1], "weight": weight,
                    "chinese": font.coveredCharacterSet.contains(UnicodeScalar(0x5B57)!),
                    "english": font.coveredCharacterSet.contains(UnicodeScalar(0x41)!)]
        }
    }
}
func render(_ doc: Document, _ output: URL) throws {
    try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
    var records = [[String: Any]]()
    for cue in doc.cues {
        let text = NSMutableAttributedString(string: "")
        var ranges = [(NSRange, String)]()
        let para = NSMutableParagraphStyle(); para.alignment = .center; para.lineBreakMode = .byWordWrapping
        for run in cue.runs {
            let start = text.length
            for char in run.text {
                let english = char.unicodeScalars.allSatisfy { $0.value < 128 }
                let name = run.font ?? (english ? doc.style.english : doc.style.chinese)
                guard let font = NSFont(name: name, size: Double(doc.width)*doc.style.size/100*cue.size*run.scale) else { throw fail("字型不存在：\(name)") }
                text.append(NSAttributedString(string: String(char), attributes: [.font: font, .foregroundColor: color(run.color ?? doc.style.color), .strokeColor: NSColor.black, .strokeWidth: -doc.style.outline*100, .paragraphStyle: para]))
            }
            ranges.append((NSRange(location: start, length: text.length-start), run.animation))
        }
        let storage = NSTextStorage(attributedString: text), layout = NSLayoutManager()
        let container = NSTextContainer(size: NSSize(width: Double(doc.width)*cue.boxWidth, height: Double(doc.height)*2))
        container.lineFragmentPadding = 0; layout.addTextContainer(container); storage.addLayoutManager(layout)
        layout.ensureLayout(for: container)
        let used = layout.usedRect(for: container)
        if used.height > Double(doc.height)*0.6 { throw fail("字幕太高，請縮小：\(cue.id)") }
        var lines = [[String: Any]]()
        layout.enumerateLineFragments(forGlyphRange: layout.glyphRange(for: container)) { rect, used, _, glyphs, _ in
            let chars = layout.characterRange(forGlyphRange: glyphs, actualGlyphRange: nil)
            lines.append(["start": chars.location, "end": chars.location+chars.length, "text": (cue.text as NSString).substring(with: chars)])
        }
        let animated = ranges.contains { $0.1 != "none" }
        let motionDuration = min(0.5, cue.end-cue.start)
        let count = animated ? max(1, Int(ceil(motionDuration*30))) : 0
        var frames = [String]()
        for frame in 0...count {
            guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: doc.width, pixelsHigh: doc.height, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0), let base = NSGraphicsContext(bitmapImageRep: bitmap) else { throw fail("無法建立字幕影格。") }
            let cg = base.cgContext
            cg.translateBy(x: 0, y: CGFloat(doc.height)); cg.scaleBy(x: 1, y: -1)
            NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = NSGraphicsContext(cgContext: cg, flipped: true)
            let rawX = Double(doc.width)*cue.x-used.width/2
            let rawY = cue.anchor == "center" ? Double(doc.height)*cue.y-used.height/2 : Double(doc.height)*cue.y-used.height
            let origin = NSPoint(x: max(0, min(Double(doc.width)-used.width, rawX)), y: max(0, min(Double(doc.height)-used.height, rawY)))
            for (range, animation) in ranges where range.length > 0 {
                let glyphs = layout.glyphRange(forCharacterRange: range, actualCharacterRange: nil)
                let bounds = layout.boundingRect(forGlyphRange: glyphs, in: container).offsetBy(dx: origin.x, dy: origin.y)
                let p = count == 0 ? 1.0 : min(1.0, Double(frame)/30/motionDuration)
                let scale = animation == "pop" ? (p >= 1 ? 1 : 0.65+0.35*p+0.17*sin(p*Double.pi)) : 1
                let dy = animation == "bounce" ? -Double(doc.width)*0.025*sin(p*Double.pi*3)*(1-p) : 0
                cg.saveGState(); cg.translateBy(x: bounds.midX, y: bounds.midY+dy); cg.scaleBy(x: scale, y: scale); cg.translateBy(x: -bounds.midX, y: -bounds.midY)
                layout.drawGlyphs(forGlyphRange: glyphs, at: origin)
                storage.addAttribute(.strokeWidth, value: 0, range: range)
                layout.drawGlyphs(forGlyphRange: glyphs, at: origin)
                storage.addAttribute(.strokeWidth, value: -doc.style.outline*100, range: range)
                cg.restoreGState()
            }
            NSGraphicsContext.restoreGraphicsState()
            let name = cue.id + "-\(frame).png"
            try bitmap.representation(using: .png, properties: [:])!.write(to: output.appendingPathComponent(name), options: .atomic)
            frames.append(name)
        }
        let ox = max(0, min(Double(doc.width)-used.width, Double(doc.width)*cue.x-used.width/2))
        let oy = max(0, min(Double(doc.height)-used.height, Double(doc.height)*cue.y-(cue.anchor == "center" ? used.height/2 : used.height)))
        let anchorHeight = cue.anchor == "center" ? used.height/2 : used.height
        records.append(["id": cue.id, "lines": lines, "frames": frames, "motionDuration": motionDuration,
                        "placement": ["x": (ox+used.width/2)/Double(doc.width), "y": (oy+anchorHeight)/Double(doc.height),
                                      "minX": used.width/2/Double(doc.width), "maxX": 1-used.width/2/Double(doc.width),
                                      "minY": anchorHeight/Double(doc.height), "maxY": 1-(used.height-anchorHeight)/Double(doc.height)]])
    }
    try JSONSerialization.data(withJSONObject: records).write(to: output.appendingPathComponent("layout.json"), options: .atomic)
}
do {
    if CommandLine.arguments.contains("--fonts") {
        FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: fonts()))
    } else {
        let doc = try JSONDecoder().decode(Document.self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
        try render(doc, URL(fileURLWithPath: CommandLine.arguments[2]))
    }
} catch { FileHandle.standardError.write(Data((error.localizedDescription+"\n").utf8)); exit(1) }
