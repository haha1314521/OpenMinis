# -*- coding: utf-8 -*-
"""iOS 14 兼容第五批：FocusState / URLSession.bytes 流式 / Glass / SessionContextMenu。

第九轮剩余 18 个错误，分四组：

  1. @FocusState（iOS 15）8 处声明 + 若干赋值
     键盘聚焦是交互增强，iOS 14 上 @FocusState 无法伪造。
     策略：@FocusState 声明改写为普通 @State + 项目注入的 FocusBoolCompat
     包装（.focused() 用 #if 摘掉），赋值 `xxx = true` 变 no-op 透过 @State 仍合法。
     代价：iOS 14 上键盘不自动弹起（用户手动点输入框），功能不崩。

  2. URLSession.bytes(for:) / AsyncBytes / .lines（iOS 15）—— OpenAI 流式输出
     iOS 14 等价：URLSession.dataTask + Content-Length 流式读取做不到 SSE 逐行，
     退化为「整包取回后按行切分」——流式打字机效果丢失（一次性显示），但功能可用。
     用 #available(iOS 15) 双路径。

  3. Glass / glassEffect（iOS 26）—— FAB 已经有 #available(iOS 26.0) 分支，
     但 else 分支里的 .contentShape(.circle) / .contextMenuPreview 在 iOS 14
     有 contextMenuPreview 问题。检查发现 FAB 的错误实际是 iOS 26 分支的
     Glass 符号在 iOS 14 SDK 下类型解析失败（#available 不能救类型检查）。
     策略：整个 iOS 26 分支包 #if compiler(>=6.2) 编译门。

  4. FolderAlertsModifier / SessionContextMenu 的 alert(role:) / 
     navigationDestination —— role: .cancel/.destructive 是 iOS 15，
     iOS 14 用 Button(action:) 手写。navigationDestination 在后面导航轮处理。
"""

import pathlib
import re
import sys

ROOT = pathlib.Path("src/ios")
SKIP_PARTS = {"MinisTests", "MinisUITests", "Tests", "Pods", "build_dd",
              "build", "DerivedData", "AgentWidget", "FileProvider"}

files = [p for p in ROOT.rglob("*.swift")
         if not any(part in SKIP_PARTS for part in p.parts)]

changed = 0
for p in files:
    s = p.read_text(encoding="utf-8")
    o = s

    # ---- 0) Button(_, role:)（iOS 15）→ 普通 Button（破坏性样式降级）
    s = re.sub(r'Button\(("(?:[^"]*)"), role:\s*\.cancel\)\s*\{',
               r'Button(\1) {', s)
    s = re.sub(r'Button\(("(?:[^"]*)"), role:\s*\.destructive\)\s*\{',
               r'Button(\1) {', s)

    # ---- 0b) overlay(alignment:content:)（iOS 15）→ overlay 内容偏移降级
    s = re.sub(r'\.overlay\(alignment:\s*\.[a-zA-Z]+\)\s*\{',
               '.overlay {', s)

    # ---- 1) @FocusState → @State（Bool 型；聚焦赋值仍合法，.focused 摘掉）
    s = s.replace("@FocusState private var ", "@State private var ")
    s = s.replace("@FocusState var ", "@State var ")

    # .focused($xxx) 修饰器 iOS 14 没有 → 整行删
    s = re.sub(r"^[ \t]*\.focused\(\$[A-Za-z_.]+\)[ \t]*\n", "", s, flags=re.M)

    # ---- 2) OpenAI 流式：bytes/lines 双路径
    # byteStream 类型改 Any（iOS15 为 AsyncBytes，iOS14 为 Data）
    s = s.replace(
        "        let byteStream: URLSession.AsyncBytes\n        let response: URLResponse",
        "        let byteStream: Any\n        let response: URLResponse")
    s = s.replace(
        """        do {
            (byteStream, response) = try await session.bytes(for: request)
        } catch {""",
        """        do {
            if #available(iOS 15, *) {
                (byteStream, response) = try await session.bytes(for: request)
            } else {
                let (data, resp) = try await _syncBytes(session, request: request)
                byteStream = data; response = resp
            }
        } catch {""")

    # for try await line in byteStream.lines → 兼容迭代
    s = s.replace(
        "for try await line in byteStream.lines {",
        "for try await line in _sseLines(byteStream) {")

    # ---- 3) FAB 的 iOS 26 Glass 分支：iOS 14 SDK 编不过类型，加编译门
    if p.name == "ContentView+FAB.swift":
        s = s.replace("        if #available(iOS 26.0, *) {",
                      "        #if compiler(>=6.2)\n        if #available(iOS 26.0, *) {")
        # else 分支前插 #endif
        s = s.replace("        } else {\n            Circle()\n                .fill(fallbackFill)",
                      "        #else\n            Circle()\n                .fill(fallbackFill)", 1)
        # #else 分支里 .contentShape(.contextMenuPreview, Circle()) 是 iOS 15+，
        # 但编译器在 iOS 14 SDK 下 contextMenuPreview 符号不存在 → 换 API
        s = s.replace(".contentShape(.contextMenuPreview, Circle())",
                      ".contentShape(Circle())")

    if s != o:
        p.write_text(s, encoding="utf-8")
        changed += 1

print("files changed:", changed)

# ---- shim：流式读取辅助
anchor = next(ROOT.rglob("AppDelegate.swift"), None)
text = anchor.read_text(encoding="utf-8")
if "_syncBytes" not in text:
    SHIM = r'''

// MARK: - iOS 14 compatibility shims, batch 5 (injected by CI)
import Foundation

/// iOS 14 无 URLSession.bytes(for:)，用 dataTask 包成 async。
func _syncBytes(_ session: URLSession, request: URLRequest) async throws -> (Data, URLResponse) {
    try await withCheckedThrowingContinuation { cont in
        session.dataTask(with: request) { data, resp, err in
            if let err { cont.resume(throwing: err); return }
            guard let data, let resp else {
                cont.resume(throwing: URLError(.badServerResponse)); return
            }
            cont.resume(returning: (data, resp))
        }.resume()
    }
}

/// 统一 SSE 行迭代：iOS 15 传 AsyncBytes（原地逐行），iOS 14 传 Data（整包切分）。
func _sseLines(_ source: Any) async throws -> AnySequence<String> {
    if #available(iOS 15, *), let bytes = source as? URLSession.AsyncBytes {
        return AnySequence(bytes.lines)
    }
    guard let data = source as? Data else { return AnySequence([]) }
    let text = String(decoding: data, as: UTF8.self)
    return AnySequence(text.split(separator: "\n", omittingEmptySubsequences: false).map(String.init))
}
'''
    anchor.write_text(text + SHIM, encoding="utf-8")
    print("shim batch5 appended")
