#!/bin/bash
# build_dmg.sh — 一键打包：PyInstaller 生成 .app + hdiutil 生成带拖拽布局的 DMG
#
# 用法：
#   bash scripts/build_dmg.sh
#
# 产物：dist/工时计算器.dmg

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="工时计算器"
APP_PATH="$PROJECT_DIR/dist/$APP_NAME.app"
DMG_PATH="$PROJECT_DIR/dist/$APP_NAME.dmg"
STAGING_DIR="$PROJECT_DIR/dist/dmg_staging"

cd "$PROJECT_DIR"

echo "=== 1/4 PyInstaller 打包 ==="
/opt/anaconda3/bin/python -m PyInstaller "$APP_NAME.spec" --noconfirm

echo "=== 2/4 准备 DMG 临时目录 ==="
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp -R "$APP_PATH" "$STAGING_DIR/"
# 创建 Applications 文件夹的软链接（拖拽目标）
ln -s /Applications "$STAGING_DIR/Applications"

echo "=== 3/4 生成 DMG ==="
rm -f "$DMG_PATH"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING_DIR" -ov -format UDZO "$DMG_PATH"

echo "=== 4/4 清理 ==="
rm -rf "$STAGING_DIR"

echo ""
echo "✅ 打包完成：$DMG_PATH"
echo "   字节数：$(stat -f%z "$DMG_PATH")"
echo "   发版时把此值填入 appcast.xml 的 length 属性"
