import re, sys, pathlib

proj = pathlib.Path("src/ios/Minis.xcodeproj/project.pbxproj")
text = proj.read_text(encoding="utf-8")

# 1) 目标 -> 构建配置 GUID
lists = {}
for m in re.finditer(r'([0-9A-F]{24})\s*/\* Build configuration list for PBXNativeTarget "([^"]+)" \*/ = \{(.*?)\n\t\t\};', text, re.S):
    guids = re.findall(r'([0-9A-F]{24})\s*/\* (?:Debug|Release) \*/', m.group(3))
    lists[m.group(2)] = guids

WANT = {"Minis": "14.0", "MinisFileProvider": "16.0", "MinisShare": "16.0",
        "AgentWidgetExtension": "16.0", "MinisTestHost": "14.0"}

changed = 0
for target, guids in lists.items():
    ver = WANT.get(target)
    if not ver:
        continue
    for g in guids:
        pat = re.compile(r'(' + g + r' /\* (?:Debug|Release) \*/ = \{.*?)(\n\t\t\};)', re.S)
        m = pat.search(text)
        if not m:
            continue
        block = m.group(1)
        if "IPHONEOS_DEPLOYMENT_TARGET" in block:
            newblock = re.sub(r'IPHONEOS_DEPLOYMENT_TARGET = [0-9.]+;', 'IPHONEOS_DEPLOYMENT_TARGET = ' + ver + ';', block)
        else:
            newblock = block.replace("buildSettings = {", "buildSettings = {\n\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = " + ver + ";", 1)
        if newblock != block:
            text = text[:m.start(1)] + newblock + text[m.end(1):]
            changed += 1

proj.write_text(text, encoding="utf-8")
print("targets:", {k: len(v) for k, v in lists.items()})
print("changed configs:", changed)
