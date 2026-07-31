"""
ui - 界面层
============

PySide6 GUI 组件，所有窗口和弹窗均在此层。
UI 层只调用 services 层，不直接操作 database / tracker / calculator。

- theme/:          深色/浅色主题与 QSS 样式表
- views/:          主窗口与对话框视图
- components/:    可复用控件
- controllers/:   UI 流程控制器
- models/:         展示状态模型
"""
