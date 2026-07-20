#!/usr/bin/env python3
"""合盖+外接显示器测试脚本：运行后每2秒记录Display状态和HIDIdleTime，持续60秒。
使用方法：
1. 运行此脚本
2. 正常使用外接显示器几秒
3. 合上盖子（外接显示器应仍亮着）
4. 等几秒后打开盖子
5. 观察输出中 Display 状态是否变化
"""
import subprocess
import re
import time
from datetime import datetime

def get_display_state():
    """通过 pmset -g assertions 检查显示器是否亮着"""
    result = subprocess.run(['pmset', '-g', 'assertions'], capture_output=True, text=True)
    for line in result.stdout.split('\n'):
        if 'Display' in line and 'Sleep' in line:
            return line.strip()
    return 'unknown'

def get_hid_idle():
    """获取 HIDIdleTime（秒）"""
    result = subprocess.run(['ioreg', '-c', 'IOHIDSystem'], capture_output=True, text=True)
    for line in result.stdout.split('\n'):
        if 'HIDIdleTime' in line:
            val = line.split('=')[-1].strip().strip('"')
            return int(val) / 1e9
    return -1

def get_recent_display_events():
    """获取最近30秒内的Display事件"""
    result = subprocess.run(['pmset', '-g', 'log'], capture_output=True, text=True)
    pattern = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \+\d{4}\s+Notification\s+Display is turned (on|off)')
    now = datetime.now()
    events = []
    for line in result.stdout.split('\n'):
        m = pattern.match(line)
        if m:
            ts = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
            diff = (now - ts).total_seconds()
            if diff < 120:
                events.append(f'  {m.group(1)} -> {m.group(2)} ({diff:.0f}s ago)')
    return events

print("=" * 60)
print("合盖+外接显示器测试")
print("=" * 60)
print()
print("操作步骤：")
print("  1. 确保外接显示器已连接并亮着")
print("  2. 等5秒（记录正常状态）")
print("  3. 合上盖子，观察外接显示器是否仍亮着")
print("  4. 等10秒")
print("  5. 打开盖子")
print("  6. 等程序结束")
print()
print("-" * 60)

start = time.time()
prev_events = set()

while time.time() - start < 60:
    elapsed = time.time() - start
    idle = get_hid_idle()
    
    # 检查新的Display事件
    events = get_recent_display_events()
    new_events = [e for e in events if e not in prev_events]
    prev_events = set(events)
    
    timestamp = datetime.now().strftime('%H:%M:%S')
    status = f"[{elapsed:5.1f}s] {timestamp} | HIDIdle: {idle:6.1f}s"
    
    if new_events:
        for e in new_events:
            status += f" | NEW EVENT:\n{e}"
    
    print(status)
    time.sleep(2)

print("-" * 60)
print("测试结束。请查看上方输出：")
print("  - 合盖后是否有 'Display is turned off' 事件？")
print("  - 如果有 → 合盖会被误判为熄屏")
print("  - 如果没有 → 合盖+外接显示器不会触发熄屏，符合预期")
