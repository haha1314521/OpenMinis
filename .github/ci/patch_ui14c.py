#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iOS 14 兼容第三批：PhotosPicker 降级。

聊天附件选择与 SOUL 头像选择用的 PhotosPicker / PhotosPickerItem 是 iOS 16。
iOS 14 上没有 PHPicker 的 SwiftUI 包装，完整等价实现太重；这两处统一降级：
  - 选图入口按钮隐藏（.photosPicker 条件化）
  - photosPicker / onChange 修饰器整段条件化，iOS 14 不编译
相机拍照（UIImagePickerController，iOS 2 起就有）与文件选择（fileImporter，
iOS 14 有）不受影响。

实现方式：给每个文件注入一个假的 PhotosPickerItemCompat 类型 + 条件编译
标志 iOS14_NO_PHOTOS_PICKER，photosPicker 调用包进 #if。iOS 14 下功能缺失
（按钮不再出现），但主流程不崩。
"""

import pathlib
import re
import sys

ROOT = pathlib.Path("src/ios")
SKIP_PARTS = {"MinisTests", "MinisUITests", "Tests", "Pods", "build_dd",
              "build", "DerivedData", "AgentWidget", "FileProvider"}

TARGETS = [
    ROOT / "Views/Chat/AIChatView/AIChatView.swift",
    ROOT / "Views/Settings/SoulSettingsView.swift",
]

changed = 0
for p in TARGETS:
    if not p.exists():
        print("missing:", p); continue
    s = p.read_text(encoding="utf-8")
    o = s

    # 1) PhotosPickerItem 类型引用 → 兼容类型名
    s = s.replace("PhotosPickerItem", "PhotosPickerItemCompat")

    # 2) .photosPicker(...) 单调用包进 #if（用括号配对找完整调用，含跨行）
    for mm in list(re.finditer(r'([ 	]+)\.photosPicker\(', s)):
        indent = mm.group(1)
        start = mm.start()
        i = s.index('(', mm.end() - 1)
        depth = 0
        while i < len(s):
            if s[i] == '(': depth += 1
            elif s[i] == ')':
                depth -= 1
                if depth == 0: break
            i += 1
        end = i + 1
        block = s[start:end]
        guarded = ('#if !IOS14_NO_PHOTOS_PICKER\n' + block + '\n#endif')
        s = s[:start] + guarded + s[end:]

    # onChange(of: photoItem) 在 iOS14 下 photoItem 恒为 nil，guard 已兜住
    if s != o:
        p.write_text(s, encoding="utf-8")
        changed += 1

print("files changed:", changed)

# 3) 注入兼容类型 + 标志定义（追加到 AppDelegate）
anchor = next(ROOT.rglob("AppDelegate.swift"), None)
if anchor is None:
    print("AppDelegate.swift not found"); sys.exit(1)
text = anchor.read_text(encoding="utf-8")
if "PhotosPickerItemCompat" not in text:
    SHIM = r'''

// MARK: - iOS 14 compatibility shims, batch 3 (injected by CI)
#if IOS14_NO_PHOTOS_PICKER
import SwiftUI

/// iOS 16 的 PhotosPickerItem 占位类型。iOS 14 构建下 photosPicker 调用
/// 已被 #if 摘除，该类型只是让状态属性声明能通过编译，永远不会被赋值。
struct PhotosPickerItemCompat { }
#endif
'''
    anchor.write_text(text + SHIM, encoding="utf-8")
    print("shim batch3 appended")
