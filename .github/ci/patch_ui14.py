import pathlib, re, sys

ROOT = pathlib.Path("src/ios")
SKIP_PARTS = {"MinisTests", "Tests", "Pods", "build_dd", "build", "DerivedData"}

# iOS 15 的 ShapeStyle 简写 → iOS 13/14 可用的 UIColor 映射
STYLE_MAP = {
    ".primary": "Color(UIColor.label)",
    ".secondary": "Color(UIColor.secondaryLabel)",
    ".tertiary": "Color(UIColor.tertiaryLabel)",
    ".quaternary": "Color(UIColor.quaternaryLabel)",
    ".tint": "Color.accentColor",
}

COMPAT = r'''

// MARK: - iOS 14 compatibility shims (injected by CI)
import SwiftUI

extension View {
    /// foregroundStyle 是 iOS 15 的 ShapeStyle 接口；调用点已把 .primary/.secondary
    /// 等映射成具体 Color，这里退回 iOS 13 就有的 foregroundColor。
    func foregroundStyleCompat(_ color: Color) -> some View {
        foregroundColor(color)
    }

    /// task 是 iOS 15；iOS 14 用 onAppear + Task 等价替代（id 变化不重跑）。
    func taskCompat(priority: TaskPriority = .userInitiated,
                    _ action: @escaping @Sendable () async -> Void) -> some View {
        onAppear { Task(priority: priority) { await action() } }
    }

    func taskCompat(id: some Equatable,
                    priority: TaskPriority = .userInitiated,
                    _ action: @escaping @Sendable () async -> Void) -> some View {
        onAppear { Task(priority: priority) { await action() } }
    }
}
'''

changed = lines = 0
for p in ROOT.rglob("*.swift"):
    if any(part in SKIP_PARTS for part in p.parts):
        continue
    s = p.read_text(encoding="utf-8")
    o = s

    # 1) foregroundStyle(.x) → foregroundStyleCompat(具体 Color)
    for k, v in STYLE_MAP.items():
        s = s.replace(".foregroundStyle(" + k + ")", ".foregroundStyleCompat(" + v + ")")
    s = s.replace(".foregroundStyle(", ".foregroundStyleCompat(")

    # 2) background(_:in:) 是 iOS 15 → background(Shape().fill(...))
    s = re.sub(r"\.background\(([^()]*(?:\([^()]*\)[^()]*)*), in: (Capsule|Circle)\(\)\)",
               r".background(\2().fill(\1))", s)

    # 3) .task/.task(id:) → taskCompat
    s = s.replace(".task(id: ", ".taskCompat(id: ")
    s = s.replace(".task(priority: ", ".taskCompat(priority: ")
    s = s.replace(".task {", ".taskCompat {")

    # 4) 工具栏位置 iOS 16 → 14
    s = s.replace(".topBarTrailing", ".navigationBarTrailing")
    s = s.replace(".topBarLeading", ".navigationBarLeading")

    # 5) listRowSeparator 是 iOS 15，只是视觉细节，整行去掉
    s = re.sub(r"^[ \t]*\.listRowSeparator\([^)]*\)[ \t]*\n", "", s, flags=re.M)

    if s != o:
        p.write_text(s, encoding="utf-8")
        changed += 1
        lines += sum(1 for a, b in zip(o.splitlines(), s.splitlines()) if a != b)
print("files changed:", changed, "lines:", lines)

anchor = next(ROOT.rglob("AppDelegate.swift"), None)
if anchor is None:
    print("AppDelegate.swift not found"); sys.exit(1)
text = anchor.read_text(encoding="utf-8")
if "foregroundStyleCompat" not in text:
    anchor.write_text(text + COMPAT, encoding="utf-8")
    print("shim appended to", anchor)
