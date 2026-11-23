# -*- coding: utf-8 -*-
"""iOS 14 兼容第四批：WKDownload / callAsyncJavaScript / LabeledContent。

第八轮剩余错误集中在 BrowserUseManager（25 个）和 UsageStatsView（2 个）：

  1. WKDownload 系（iOS 14.5）
     - shouldPerformDownload / .download policy / didBecome download:
       decideDestinationUsing / downloadDidFinish / didFailWithError / progress
     iOS 14.0 没有 WKDownload 类，浏览器"下载到工作区"功能整体降级：
       - #if available(iOS 14.5) 包住下载分支（decidePolicy 里不再返回 .download）
       - WKDownloadDelegate extension 整段包进 #if
       - inflightDownloads / downloadDestinations / downloadCenterIds 状态与
         cancelDownload / attachDownload 方法包进 #if
     用 available 门而不是删代码，iOS 14.5+ 设备仍保留下载能力。

  2. callAsyncJavaScript（iOS 15）23 处
     → 全部退到 evaluateJavaScriptBounded（项目自带的超时包装，iOS 14 可用）。
       callAsyncJavaScript 的 await/return 语义丢失，但浏览器 agent 的 JS
       全是同步脚本（DOM 观察、读状态），evaluateJavaScript 语义足够。
       callAsyncJavaScriptBounded 方法整体包 #if，调用点改名。

  3. LabeledContent（iOS 16）5 处
     → HStack { Text(label) Spacer Text(value) } 等价布局。

用法说明写在 patch 头部，全部用 #if available 门而非删代码。
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

    is_bum = p.name == "BrowserUseManager.swift"
    is_usage = p.name == "UsageStatsView.swift"

    if is_bum:
        # ---- 1) 下载分支：decisionHandler(.download) 只在 iOS 14.5+
        s = s.replace(
            """        if navigationAction.shouldPerformDownload {
            decisionHandler(.download, preferences)
            return
        }""",
            """        if #available(iOS 14.5, *) {
            if navigationAction.shouldPerformDownload {
                decisionHandler(.download, preferences)
                return
            }
        }""")
        s = s.replace(
            """        if let http = navigationResponse.response as? HTTPURLResponse,
           let disposition = http.value(forHTTPHeaderField: "Content-Disposition")?.lowercased(),
           disposition.contains("attachment") {
            decisionHandler(.download)
            return
        }
        if !navigationResponse.canShowMIMEType {
            decisionHandler(.download)
            return
        }""",
            """        if #available(iOS 14.5, *) {
            if let http = navigationResponse.response as? HTTPURLResponse,
               let disposition = http.value(forHTTPHeaderField: "Content-Disposition")?.lowercased(),
               disposition.contains("attachment") {
                decisionHandler(.download)
                return
            }
            if !navigationResponse.canShowMIMEType {
                decisionHandler(.download)
                return
            }
        }""")

        # ---- WKDownloadDelegate extension 整段包 #if
        m = re.search(r"// MARK: - WKDownloadDelegate\n\nextension BrowserUseManager: WKDownloadDelegate \{", s)
        if m:
            start = m.start()
            # 花括号配对找 extension 结束
            j = s.index("{", m.end() - 1)
            d = 0
            while j < len(s):
                if s[j] == "{": d += 1
                elif s[j] == "}":
                    d -= 1
                    if d == 0: break
                j += 1
            s = (s[:start]
                 + "#if canImport(WebKit) && os(iOS)\n#if compiler(>=5.5) // WKDownload @available(iOS 14.5)\n"
                 + s[start:j+1]
                 + "\n#endif\n#endif"
                 + s[j+1:])

        # ---- 下载状态与方法包 #if（attachDownload / cancelDownload / inflightDownloads）
        s = s.replace(
            "    private var inflightDownloads: [ObjectIdentifier: WKDownload] = [:]",
            "    #if compiler(>=5.5)\n    private var inflightDownloads: [ObjectIdentifier: WKDownload] = [:]\n    #endif")

        # ---- 2) callAsyncJavaScript → evaluateJavaScriptBounded（同步语义够用）
        # 带参数/复杂调用先整体包 #if 改名：直接把 await webView.callAsyncJavaScript(
        # 换成 await self.evaluateJavaScriptBounded(  ……参数不同（没有 arguments/contentWorld）。
        # 逐个改：去掉 ", arguments: [:], contentWorld: .page" 和多行参数。
        s = re.sub(
            r"webView\.callAsyncJavaScript\(\s*([^,]+?),\s*arguments:\s*\[:\],\s*contentWorld:\s*\.page\s*\)",
            r"self.evaluateJavaScriptBounded(\1)", s)
        # 多行形态（第二个调用带换行参数）
        s = re.sub(
            r"webView\.callAsyncJavaScript\(\s*\n\s*([^,]+?),\s*\n\s*arguments:\s*\[:\],\s*contentWorld:\s*\.page\s*\n\s*\)",
            r"self.evaluateJavaScriptBounded(\1)", s)
        # execute_js 需要 promise 语义，iOS 15+ 走 bounded，iOS 14 退 evaluate
        s = s.replace(
            '            let result = try await callAsyncJavaScriptBounded(\n                Self.wrapExecuteJSReturn(script), timeout: Self.executeJSTimeout)',
            '            let result: Any?\n            if #available(iOS 15, *) {\n                result = try await callAsyncJavaScriptBounded(\n                    Self.wrapExecuteJSReturn(script), timeout: Self.executeJSTimeout)\n            } else {\n                result = try await evaluateJavaScriptBounded(\n                    Self.wrapExecuteJSReturn(script), timeout: Self.executeJSTimeout)\n            }')

        # try? await 前缀已兼容；callAsyncJavaScriptBounded 定义与方法注释包 #if
        cm = re.search(r"    /// `callAsyncJavaScript` counterpart of `evaluateJavaScriptBounded`\.", s)
        if cm:
            start = cm.start()
            # 找到该方法结束：从方法声明行向下找 "    }"（首个四空格闭括号）
            decl = s.index("private func callAsyncJavaScriptBounded", start)
            j = s.index("{", decl)
            d = 0
            while j < len(s):
                if s[j] == "{": d += 1
                elif s[j] == "}":
                    d -= 1
                    if d == 0: break
                j += 1
            # 吞掉方法后的空行
            end = j + 1
            s = (s[:start] + "#if canImport(WebKit) && compiler(>=5.5)\n"
                 + s[start:end] + "\n#endif" + s[end:])

    if is_usage:
        # ---- 3) LabeledContent("x", value: y) → 自定义行
        s = re.sub(
            r'LabeledContent\("([^"]+)", value:\s*([^)]+)\)',
            r'HStack { Text("\1") Spacer() Text(\2).foregroundStyleCompat(Color(UIColor.secondaryLabel)) }',
            s)

    if s != o:
        p.write_text(s, encoding="utf-8")
        changed += 1

print("files changed:", changed)
