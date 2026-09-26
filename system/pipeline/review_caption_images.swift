import AppKit
import Foundation

struct RunStyle: Decodable {
    let fontFamily: String?
    let sizeScale: Double?
    let color: String?
}
struct Run: Decodable { let text: String; let style: RunStyle }
struct Cue: Decodable { let id: Int; let text: String; let runs: [Run] }
struct GlobalStyle: Decodable {
    let fontFamily: String
    let sizePct: Double
    let weight: Int
    let color: String
    let strokePct: Double
    let strokeColor: String
    let bottomPct: Double
}
struct Document: Decodable { let style: GlobalStyle; let cues: [Cue] }

func argument(_ name: String) throws -> String {
    guard let index = CommandLine.arguments.firstIndex(of: name), index + 1 < CommandLine.arguments.count else {
        throw NSError(domain: "ReviewCaption", code: 2, userInfo: [NSLocalizedDescriptionKey: "Missing \(name)"])
    }
    return CommandLine.arguments[index + 1]
}

func color(_ hex: String) throws -> NSColor {
    guard hex.count == 7, hex.first == "#", let value = Int(hex.dropFirst(), radix: 16) else {
        throw NSError(domain: "ReviewCaption", code: 3, userInfo: [NSLocalizedDescriptionKey: "Invalid color"])
    }
    return NSColor(calibratedRed: CGFloat((value >> 16) & 255) / 255,
                   green: CGFloat((value >> 8) & 255) / 255,
                   blue: CGFloat(value & 255) / 255, alpha: 1)
}

func font(_ family: String, size: Double, weight: Int) throws -> NSFont {
    guard NSFontManager.shared.availableFontFamilies.contains(family) else {
        throw NSError(domain: "ReviewCaption", code: 4, userInfo: [NSLocalizedDescriptionKey: "Unavailable font: \(family)"])
    }
    let base = NSFont.systemFont(ofSize: CGFloat(size), weight: NSFont.Weight(rawValue: CGFloat(weight - 400) / 1000))
    return NSFontManager.shared.convert(base, toFamily: family)
}

func render(_ cue: Cue, document: Document, width: Int, height: Int, output: URL) throws {
    guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
                                        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                        isPlanar: false, colorSpaceName: .deviceRGB,
                                        bytesPerRow: 0, bitsPerPixel: 0),
          let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
        throw NSError(domain: "ReviewCaption", code: 6)
    }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    NSColor.clear.setFill()
    NSRect(x: 0, y: 0, width: width, height: height).fill()
    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = .center
    paragraph.lineBreakMode = .byWordWrapping
    let baseSize = Double(width) * document.style.sizePct / 100
    let attributed = NSMutableAttributedString()
    for run in cue.runs {
        let runSize = baseSize * (run.style.sizeScale ?? 1)
        let attributes: [NSAttributedString.Key: Any] = [
            .font: try font(run.style.fontFamily ?? document.style.fontFamily, size: runSize, weight: document.style.weight),
            .foregroundColor: try color(run.style.color ?? document.style.color),
            .strokeColor: try color(document.style.strokeColor),
            .strokeWidth: -document.style.strokePct * 100,
            .paragraphStyle: paragraph,
        ]
        attributed.append(NSAttributedString(string: run.text, attributes: attributes))
    }
    let maxWidth = CGFloat(width) * 0.96
    let measured = attributed.boundingRect(with: NSSize(width: maxWidth, height: CGFloat(height)),
                                            options: [.usesLineFragmentOrigin, .usesFontLeading])
    guard measured.height <= CGFloat(height) * 0.45 else {
        NSGraphicsContext.restoreGraphicsState()
        throw NSError(domain: "ReviewCaption", code: 5, userInfo: [NSLocalizedDescriptionKey: "Caption does not fit"])
    }
    let y = CGFloat(height) * document.style.bottomPct / 100
    let textRect = NSRect(x: CGFloat(width) * 0.02, y: y, width: maxWidth,
                          height: ceil(measured.height) + baseSize * 0.4)
    attributed.draw(with: textRect, options: [.usesLineFragmentOrigin, .usesFontLeading])
    // AppKit centers a text stroke on the glyph edge. Repaint the fill last so
    // thicker outlines do not erase white lettering (CSS paint-order: stroke fill).
    let fill = NSMutableAttributedString(attributedString: attributed)
    fill.addAttribute(.strokeWidth, value: 0, range: NSRange(location: 0, length: fill.length))
    fill.draw(with: textRect, options: [.usesLineFragmentOrigin, .usesFontLeading])
    NSGraphicsContext.restoreGraphicsState()
    guard let png = bitmap.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "ReviewCaption", code: 6, userInfo: [NSLocalizedDescriptionKey: "PNG encoding failed"])
    }
    try png.write(to: output, options: .atomic)
}

func renderBlank(width: Int, height: Int, output: URL) throws {
    guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
                                        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                        isPlanar: false, colorSpaceName: .deviceRGB,
                                        bytesPerRow: 0, bitsPerPixel: 0),
          let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
        throw NSError(domain: "ReviewCaption", code: 6)
    }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    NSColor.clear.setFill()
    NSRect(x: 0, y: 0, width: width, height: height).fill()
    NSGraphicsContext.restoreGraphicsState()
    guard let png = bitmap.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "ReviewCaption", code: 6, userInfo: [NSLocalizedDescriptionKey: "PNG encoding failed"])
    }
    try png.write(to: output, options: .atomic)
}

do {
    let input = URL(fileURLWithPath: try argument("--input"))
    let output = URL(fileURLWithPath: try argument("--output-dir"), isDirectory: true)
    let width = Int(try argument("--width")) ?? 0
    let height = Int(try argument("--height")) ?? 0
    guard width > 0, height > 0 else { throw NSError(domain: "ReviewCaption", code: 7) }
    let document = try JSONDecoder().decode(Document.self, from: Data(contentsOf: input))
    try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
    try renderBlank(width: width, height: height, output: output.appendingPathComponent("blank.png"))
    for (index, cue) in document.cues.enumerated() {
        try render(cue, document: document, width: width, height: height,
                   output: output.appendingPathComponent(String(format: "caption-%04d.png", index + 1)))
    }
} catch {
    FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
    exit(1)
}
