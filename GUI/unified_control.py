import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import queue
import pygame
from pynput import keyboard
from robodog import Dog, UserMode
import sys
import os

class RobodogUnifiedGUI:
    def __init__(self):
        # 连接参数
        self.host = '192.168.118.29'
        self.dog = None
        self.connected = False
        self.running = False
        
        # 控制模式
        self.control_modes = ["键盘控制", "手柄控制", "GUI按钮控制"]
        self.current_mode = "键盘控制"
        
        # pygame相关 (手柄)
        self.joystick = None
        self.gamepad_connected = False
        self.pygame_initialized = False
        
        # 键盘监听
        self.keyboard_listener = None
        self.pressed_keys = set()
        self.gui_pressed_keys = set()  # GUI按钮按下状态
        
        # 控制参数
        self.speed_levels = [0.2, 0.5, 0.8, 1.2, 1.5, 2.0]
        self.current_speed_index = 2
        self.max_turn_speed = 1.0
        self.height_levels = [0.15, 0.20, 0.25, 0.30, 0.35]
        self.current_height_index = 2
        self.deadzone = 0.1  # 手柄死区
        
        # 当前状态
        self.current_vx = 0.0
        self.current_vy = 0.0
        self.current_wz = 0.0
        self.current_height = self.height_levels[self.current_height_index]
        
        # 消息队列
        self.message_queue = queue.Queue()
        
        # 控制线程
        self.control_thread = None
        
        # 移动键映射
        self.movement_keys = {
            'w': {'vx': 1.0, 'vy': 0.0, 'wz': 0.0, 'name': '前进'},
            's': {'vx': -1.0, 'vy': 0.0, 'wz': 0.0, 'name': '后退'},
            'a': {'vx': 0.0, 'vy': 1.0, 'wz': 0.0, 'name': '左移'},
            'd': {'vx': 0.0, 'vy': -1.0, 'wz': 0.0, 'name': '右移'},
            'q': {'vx': 0.0, 'vy': 0.0, 'wz': 1.0, 'name': '左转'},
            'e': {'vx': 0.0, 'vy': 0.0, 'wz': -1.0, 'name': '右转'},
        }
        
        # 方向键映射
        self.arrow_keys = {
            'Up': 'w',
            'Down': 's', 
            'Left': 'a',
            'Right': 'd',
        }
        
        # 手柄按钮映射
        self.button_map = {
            0: 'A', 1: 'B', 2: 'X', 3: 'Y',
            4: 'LB', 5: 'RB', 6: 'BACK', 7: 'START',
            8: 'LS', 9: 'RS',
        }
        
        # 初始化pygame (手柄支持)
        self.init_pygame()
        
        # 设置GUI
        self.setup_gui()
        
    def init_pygame(self):
        """初始化pygame和手柄"""
        try:
            pygame.init()
            pygame.joystick.init()
            self.pygame_initialized = True
            self.check_gamepad()
        except Exception as e:
            print(f"初始化pygame失败: {e}")
            self.pygame_initialized = False
    
    def check_gamepad(self):
        """检查游戏手柄连接"""
        if not self.pygame_initialized:
            return
            
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.gamepad_connected = True
            self.message_queue.put(('gamepad_status', f"已连接手柄: {self.joystick.get_name()}"))
        else:
            self.gamepad_connected = False
            self.message_queue.put(('gamepad_status', "未检测到游戏手柄"))
    
    def setup_gui(self):
        """设置GUI界面"""
        self.root = tk.Tk()
        self.root.title("机器狗统一控制中心 v3.0")
        self.root.geometry("1200x800")
        self.root.resizable(True, True)
        
        # 设置样式
        style = ttk.Style()
        style.theme_use('clam')
        
        # 创建主容器和滚动条
        self.setup_scrollable_frame()
        
        # 设置各个区域
        self.setup_connection_area()
        self.setup_control_mode_area()
        self.setup_parameters_area()
        self.setup_keyboard_area()
        self.setup_gamepad_area()
        self.setup_gui_buttons_area()
        self.setup_status_area()
        
        # 设置键盘事件
        self.root.bind('<KeyPress>', self.on_gui_key_press)
        self.root.bind('<KeyRelease>', self.on_gui_key_release)
        self.root.focus_set()
        
        # 窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_scrollable_frame(self):
        """设置可滚动的主框架"""
        # 创建Canvas和Scrollbar
        self.canvas = tk.Canvas(self.root)
        self.scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # 布局
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # 鼠标滚轮支持
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        
        # 主内容框架
        self.main_frame = ttk.Frame(self.scrollable_frame, padding="10")
        self.main_frame.pack(fill="both", expand=True)
        
    def _on_mousewheel(self, event):
        """鼠标滚轮事件"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def setup_connection_area(self):
        """设置连接控制区域"""
        conn_frame = ttk.LabelFrame(self.main_frame, text="🔗 机器狗连接", padding="10")
        conn_frame.pack(fill="x", pady=(0, 10))
        
        # 连接控制行
        conn_row = ttk.Frame(conn_frame)
        conn_row.pack(fill="x")
        
        ttk.Label(conn_row, text="机器狗IP:").pack(side="left", padx=(0, 5))
        self.ip_var = tk.StringVar(value=self.host)
        ip_entry = ttk.Entry(conn_row, textvariable=self.ip_var, width=20)
        ip_entry.pack(side="left", padx=(0, 10))
        
        self.connect_btn = ttk.Button(conn_row, text="连接", command=self.toggle_connection)
        self.connect_btn.pack(side="left", padx=(0, 10))
        
        self.connection_status_label = ttk.Label(conn_row, text="未连接")
        self.connection_status_label.pack(side="left", padx=(0, 10))
        
        self.connection_indicator = tk.Canvas(conn_row, width=20, height=20)
        self.connection_indicator.pack(side="left")
        self.update_connection_indicator(False)
    
    def setup_control_mode_area(self):
        """设置控制模式选择区域"""
        mode_frame = ttk.LabelFrame(self.main_frame, text="🎮 控制模式", padding="10")
        mode_frame.pack(fill="x", pady=(0, 10))
        
        # 模式选择
        mode_row = ttk.Frame(mode_frame)
        mode_row.pack(fill="x")
        
        ttk.Label(mode_row, text="控制模式:").pack(side="left", padx=(0, 10))
        
        self.mode_var = tk.StringVar(value=self.current_mode)
        for mode in self.control_modes:
            ttk.Radiobutton(mode_row, text=mode, variable=self.mode_var, 
                           value=mode, command=self.on_mode_change).pack(side="left", padx=(0, 15))
        
        # 模式状态
        self.mode_status_frame = ttk.Frame(mode_frame)
        self.mode_status_frame.pack(fill="x", pady=(10, 0))
        
        self.keyboard_status_label = ttk.Label(self.mode_status_frame, text="键盘监听: 关闭")
        self.keyboard_status_label.pack(side="left", padx=(0, 20))
        
        self.gamepad_status_label = ttk.Label(self.mode_status_frame, text="手柄: 未连接")
        self.gamepad_status_label.pack(side="left", padx=(0, 20))
        
        self.gamepad_indicator = tk.Canvas(self.mode_status_frame, width=15, height=15)
        self.gamepad_indicator.pack(side="left", padx=(0, 10))
        self.update_gamepad_indicator(False)
        
        ttk.Button(self.mode_status_frame, text="刷新手柄", 
                  command=self.refresh_gamepad).pack(side="left")
    
    def setup_parameters_area(self):
        """设置控制参数区域"""
        params_frame = ttk.LabelFrame(self.main_frame, text="⚙️ 控制参数", padding="10")
        params_frame.pack(fill="x", pady=(0, 10))
        
        # 第一行：速度和高度
        row1 = ttk.Frame(params_frame)
        row1.pack(fill="x", pady=(0, 10))
        
        # 速度控制
        speed_frame = ttk.Frame(row1)
        speed_frame.pack(side="left", fill="x", expand=True, padx=(0, 20))
        
        self.speed_var = tk.StringVar(value=f"速度: {self.speed_levels[self.current_speed_index]:.1f} m/s")
        ttk.Label(speed_frame, textvariable=self.speed_var).pack()
        speed_scale = ttk.Scale(speed_frame, from_=0, to=len(self.speed_levels)-1, 
                               orient="horizontal", command=self.on_speed_change)
        speed_scale.set(self.current_speed_index)
        speed_scale.pack(fill="x")
        
        # 高度控制
        height_frame = ttk.Frame(row1)
        height_frame.pack(side="left", fill="x", expand=True)
        
        self.height_var = tk.StringVar(value=f"身高: {self.height_levels[self.current_height_index]:.2f} m")
        ttk.Label(height_frame, textvariable=self.height_var).pack()
        height_scale = ttk.Scale(height_frame, from_=0, to=len(self.height_levels)-1,
                                orient="horizontal", command=self.on_height_change)
        height_scale.set(self.current_height_index)
        height_scale.pack(fill="x")
        
        # 第二行：手柄特有参数
        row2 = ttk.Frame(params_frame)
        row2.pack(fill="x")
        
        # 转向速度
        turn_frame = ttk.Frame(row2)
        turn_frame.pack(side="left", fill="x", expand=True, padx=(0, 20))
        
        ttk.Label(turn_frame, text=f"转向速度: {self.max_turn_speed:.1f} rad/s").pack()
        self.turn_var = tk.DoubleVar(value=self.max_turn_speed)
        turn_scale = ttk.Scale(turn_frame, from_=0.3, to=2.0, variable=self.turn_var,
                              orient="horizontal", command=self.on_turn_change)
        turn_scale.pack(fill="x")
        
        # 死区控制
        deadzone_frame = ttk.Frame(row2)
        deadzone_frame.pack(side="left", fill="x", expand=True)
        
        ttk.Label(deadzone_frame, text=f"摇杆死区: {self.deadzone:.2f}").pack()
        self.deadzone_var = tk.DoubleVar(value=self.deadzone)
        deadzone_scale = ttk.Scale(deadzone_frame, from_=0.0, to=0.3, variable=self.deadzone_var,
                                  orient="horizontal", command=self.on_deadzone_change)
        deadzone_scale.pack(fill="x")
    
    def setup_keyboard_area(self):
        """设置键盘控制区域"""
        keyboard_frame = ttk.LabelFrame(self.main_frame, text="⌨️ 键盘控制", padding="10")
        keyboard_frame.pack(fill="x", pady=(0, 10))
        
        # 说明文本
        desc_text = ("键盘控制说明（即按即走模式）:\n"
                    "WASD / 方向键: 移动控制 | QE: 旋转 | ZX: 身高调节 | +-: 速度调节 | 空格: 停止 | R: 重置")
        ttk.Label(keyboard_frame, text=desc_text, foreground="gray").pack(anchor="w")
        
        # 控制按钮
        keyboard_btn_frame = ttk.Frame(keyboard_frame)
        keyboard_btn_frame.pack(fill="x", pady=(10, 0))
        
        self.start_keyboard_btn = ttk.Button(keyboard_btn_frame, text="启动键盘监听", 
                                           command=self.toggle_keyboard_listener)
        self.start_keyboard_btn.pack(side="left", padx=(0, 10))
        
        self.keyboard_indicator = tk.Canvas(keyboard_btn_frame, width=15, height=15)
        self.keyboard_indicator.pack(side="left", padx=(0, 10))
        self.update_keyboard_indicator(False)
    
    def setup_gamepad_area(self):
        """设置手柄控制区域"""
        gamepad_frame = ttk.LabelFrame(self.main_frame, text="🎮 手柄控制", padding="10")
        gamepad_frame.pack(fill="x", pady=(0, 10))
        
        # 左右两列布局
        cols_frame = ttk.Frame(gamepad_frame)
        cols_frame.pack(fill="x")
        
        # 左列 - 摇杆说明
        left_col = ttk.Frame(cols_frame)
        left_col.pack(side="left", fill="x", expand=True, padx=(0, 20))
        
        ttk.Label(left_col, text="摇杆控制:", font=("Arial", 10, "bold")).pack(anchor="w")
        stick_controls = [
            "• 左摇杆: 前后左右移动",
            "• 右摇杆: 左右旋转"
        ]
        for control in stick_controls:
            ttk.Label(left_col, text=control).pack(anchor="w")
        
        # 右列 - 按钮说明
        right_col = ttk.Frame(cols_frame)
        right_col.pack(side="left", fill="x", expand=True)
        
        ttk.Label(right_col, text="按钮控制:", font=("Arial", 10, "bold")).pack(anchor="w")
        button_controls = [
            "• Y: 升高身体  • A: 降低身体",
            "• B: 紧急停止  • X: 重置姿态"
        ]
        for control in button_controls:
            ttk.Label(right_col, text=control).pack(anchor="w")
    
    def setup_gui_buttons_area(self):
        """设置GUI按钮控制区域"""
        gui_frame = ttk.LabelFrame(self.main_frame, text="🖱️ 按钮控制", padding="10")
        gui_frame.pack(fill="x", pady=(0, 10))
        
        # 移动按钮网格
        button_grid = ttk.Frame(gui_frame)
        button_grid.pack()
        
        # 创建移动按钮
        self.move_buttons = {}
        
        # 按钮配置
        button_config = [
            ('q', '左转', 0, 0),
            ('w', '前进', 0, 1),
            ('e', '右转', 0, 2),
            ('a', '左移', 1, 0),
            ('s', '后退', 1, 1),
            ('d', '右移', 1, 2),
        ]
        
        for key, text, row, col in button_config:
            btn = ttk.Button(button_grid, text=text, width=8)
            btn.grid(row=row, column=col, padx=2, pady=2)
            btn.bind('<Button-1>', lambda e, k=key: self.on_button_press(k))
            btn.bind('<ButtonRelease-1>', lambda e, k=key: self.on_button_release(k))
            self.move_buttons[key] = btn
    
    def setup_status_area(self):
        """设置状态显示和控制区域"""
        status_frame = ttk.LabelFrame(self.main_frame, text="📊 状态监控与控制", padding="10")
        status_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # 控制按钮行
        control_row = ttk.Frame(status_frame)
        control_row.pack(fill="x", pady=(0, 10))
        
        self.start_btn = ttk.Button(control_row, text="开始控制", command=self.start_control,
                                   state="disabled")
        self.start_btn.pack(side="left", padx=(0, 10))
        
        self.stop_btn = ttk.Button(control_row, text="停止控制", command=self.stop_control,
                                  state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 10))
        
        ttk.Button(control_row, text="紧急停止", command=self.emergency_stop).pack(side="left", padx=(0, 10))
        ttk.Button(control_row, text="重置姿态", command=self.reset_posture).pack(side="left", padx=(0, 10))
        ttk.Button(control_row, text="清空日志", command=self.clear_log).pack(side="left")
        
        # 状态显示文本框
        self.status_text = tk.Text(status_frame, height=12, width=80, state='disabled',
                                  font=("Consolas", 9), wrap=tk.WORD)
        scrollbar_status = ttk.Scrollbar(status_frame, orient="vertical", command=self.status_text.yview)
        self.status_text.configure(yscrollcommand=scrollbar_status.set)
        
        # 布局状态文本框和滚动条
        text_frame = ttk.Frame(status_frame)
        text_frame.pack(fill="both", expand=True)
        
        self.status_text.pack(side="left", fill="both", expand=True)
        scrollbar_status.pack(side="right", fill="y")
    
    # 事件处理方法
    def on_mode_change(self):
        """控制模式改变"""
        self.current_mode = self.mode_var.get()
        self.log_message(f"切换到控制模式: {self.current_mode}")
        
        # 根据模式启用/禁用相应功能
        if self.current_mode == "键盘控制":
            if not self.keyboard_listener:
                self.toggle_keyboard_listener()
        elif self.current_mode == "手柄控制":
            if self.keyboard_listener:
                self.toggle_keyboard_listener()
    
    def on_speed_change(self, value):
        """速度改变"""
        self.current_speed_index = int(float(value))
        self.speed_var.set(f"速度: {self.speed_levels[self.current_speed_index]:.1f} m/s")
        
    def on_height_change(self, value):
        """高度改变"""
        self.current_height_index = int(float(value))
        self.current_height = self.height_levels[self.current_height_index]
        self.height_var.set(f"身高: {self.current_height:.2f} m")
        
    def on_turn_change(self, value):
        """转向速度改变"""
        self.max_turn_speed = float(value)
        
    def on_deadzone_change(self, value):
        """死区改变"""
        self.deadzone = float(value)
    
    # 键盘控制相关方法
    def toggle_keyboard_listener(self):
        """切换键盘监听状态"""
        if self.keyboard_listener is None:
            self.start_keyboard_listener()
        else:
            self.stop_keyboard_listener()
    
    def start_keyboard_listener(self):
        """启动键盘监听"""
        try:
            self.keyboard_listener = keyboard.Listener(
                on_press=self.on_keyboard_press,
                on_release=self.on_keyboard_release
            )
            self.keyboard_listener.start()
            self.start_keyboard_btn.configure(text="停止键盘监听")
            self.keyboard_status_label.configure(text="键盘监听: 开启")
            self.update_keyboard_indicator(True)
            self.log_message("键盘监听已启动")
        except Exception as e:
            self.log_message(f"启动键盘监听失败: {e}")
    
    def stop_keyboard_listener(self):
        """停止键盘监听"""
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
            self.pressed_keys.clear()
            self.start_keyboard_btn.configure(text="启动键盘监听")
            self.keyboard_status_label.configure(text="键盘监听: 关闭")
            self.update_keyboard_indicator(False)
            self.log_message("键盘监听已停止")
    
    def on_keyboard_press(self, key):
        """键盘按下事件"""
        try:
            k = key.char.lower() if hasattr(key, 'char') and key.char else str(key)
        except AttributeError:
            k = str(key).replace('Key.', '')
        
        if k in self.arrow_keys:
            k = self.arrow_keys[k]
        
        if k in self.movement_keys:
            self.pressed_keys.add(k)
        elif k == 'space':
            self.emergency_stop()
        elif k == 'r':
            self.reset_posture()
    
    def on_keyboard_release(self, key):
        """键盘释放事件"""
        try:
            k = key.char.lower() if hasattr(key, 'char') and key.char else str(key)
        except AttributeError:
            k = str(key).replace('Key.', '')
        
        if k in self.arrow_keys:
            k = self.arrow_keys[k]
        
        if k in self.movement_keys:
            self.pressed_keys.discard(k)
    
    def on_gui_key_press(self, event):
        """GUI键盘按下事件"""
        if self.current_mode != "键盘控制":
            return
            
        key = event.keysym.lower()
        if key in self.movement_keys:
            self.pressed_keys.add(key)
        elif key == 'space':
            self.emergency_stop()
        elif key == 'r':
            self.reset_posture()
            
    def on_gui_key_release(self, event):
        """GUI键盘释放事件"""
        if self.current_mode != "键盘控制":
            return
            
        key = event.keysym.lower()
        if key in self.movement_keys:
            self.pressed_keys.discard(key)
    
    # GUI按钮控制相关方法
    def on_button_press(self, key):
        """GUI按钮按下"""
        self.gui_pressed_keys.add(key)
        if key in self.move_buttons:
            self.move_buttons[key].configure(style='Pressed.TButton')
        
    def on_button_release(self, key):
        """GUI按钮释放"""
        self.gui_pressed_keys.discard(key)
        if key in self.move_buttons:
            self.move_buttons[key].configure(style='TButton')
    
    # 手柄控制相关方法
    def refresh_gamepad(self):
        """刷新手柄连接"""
        if not self.pygame_initialized:
            self.log_message("pygame未初始化，无法刷新手柄")
            return
            
        self.log_message("正在刷新手柄连接...")
        pygame.joystick.quit()
        pygame.joystick.init()
        self.check_gamepad()
    
    def apply_deadzone(self, value):
        """应用手柄死区"""
        if abs(value) < self.deadzone:
            return 0.0
        return value
    
    def get_movement_from_gamepad(self):
        """从手柄获取移动数据"""
        if not self.gamepad_connected or not self.joystick:
            return 0.0, 0.0, 0.0
            
        pygame.event.pump()
        
        left_x = self.apply_deadzone(self.joystick.get_axis(0))
        left_y = self.apply_deadzone(-self.joystick.get_axis(1))
        right_x = self.apply_deadzone(self.joystick.get_axis(2))
        
        current_speed = self.speed_levels[self.current_speed_index]
        vx = left_y * current_speed
        vy = left_x * current_speed
        wz = right_x * self.max_turn_speed
        
        return vx, vy, wz
    
    def handle_gamepad_buttons(self):
        """处理手柄按钮"""
        if not self.gamepad_connected or not self.joystick:
            return
            
        pygame.event.pump()
        
        if not hasattr(self, '_button_states'):
            self._button_states = {}
        
        for i in range(self.joystick.get_numbuttons()):
            current_state = self.joystick.get_button(i)
            previous_state = self._button_states.get(i, False)
            
            if current_state and not previous_state:
                button_name = self.button_map.get(i, f'Button{i}')
                
                if button_name == 'Y' and self.current_height_index < len(self.height_levels) - 1:
                    self.current_height_index += 1
                    self.current_height = self.height_levels[self.current_height_index]
                    self.height_var.set(f"身高: {self.current_height:.2f} m")
                    self.log_message(f"身高升高: {self.current_height:.2f}m")
                    
                elif button_name == 'A' and self.current_height_index > 0:
                    self.current_height_index -= 1
                    self.current_height = self.height_levels[self.current_height_index]
                    self.height_var.set(f"身高: {self.current_height:.2f} m")
                    self.log_message(f"身高降低: {self.current_height:.2f}m")
                    
                elif button_name == 'B':
                    self.emergency_stop()
                elif button_name == 'X':
                    self.reset_posture()
                elif button_name == 'START':
                    self.stop_control()
            
            self._button_states[i] = current_state
    
    # 连接控制相关方法
    def toggle_connection(self):
        """切换连接状态"""
        if not self.connected:
            self.connect_to_dog()
        else:
            self.disconnect_from_dog()
    
    def connect_to_dog(self):
        """连接到机器狗"""
        self.host = self.ip_var.get()
        self.log_message(f"正在连接到机器狗 {self.host}...")
        
        try:
            self.dog = Dog(host=self.host)
            self.dog.__enter__()
            self.dog.set_user_mode(UserMode.NORMAL)
            
            self.connected = True
            self.connect_btn.configure(text="断开连接")
            self.connection_status_label.configure(text="已连接")
            self.update_connection_indicator(True)
            self.start_btn.configure(state="normal")
            
            self.log_message("✓ 成功连接到机器狗")
            
        except Exception as e:
            self.log_message(f"✗ 连接失败: {e}")
            messagebox.showerror("连接错误", f"无法连接到机器狗:\n{e}")
    
    def disconnect_from_dog(self):
        """断开机器狗连接"""
        self.stop_control()
        
        if self.dog:
            try:
                self.dog.vx = 0.0
                self.dog.vy = 0.0
                self.dog.wz = 0.0
                self.dog.body_height = 0.23
                self.dog.__exit__(None, None, None)
            except:
                pass
            finally:
                self.dog = None
        
        self.connected = False
        self.connect_btn.configure(text="连接")
        self.connection_status_label.configure(text="未连接")
        self.update_connection_indicator(False)
        self.start_btn.configure(state="disabled")
        
        self.log_message("已断开机器狗连接")
    
    def start_control(self):
        """开始控制"""
        if not self.connected:
            messagebox.showwarning("警告", "请先连接机器狗")
            return
        
        if self.current_mode == "手柄控制" and not self.gamepad_connected:
            messagebox.showwarning("警告", "手柄控制模式需要连接游戏手柄")
            return
        
        self.running = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        
        self.control_thread = threading.Thread(target=self.control_loop)
        self.control_thread.daemon = True
        self.control_thread.start()
        
        self.log_message(f"开始 {self.current_mode}")
    
    def stop_control(self):
        """停止控制"""
        self.running = False
        
        if self.control_thread and self.control_thread.is_alive():
            self.control_thread.join(timeout=1)
        
        if self.dog:
            self.dog.vx = 0.0
            self.dog.vy = 0.0
            self.dog.wz = 0.0
        
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        
        self.log_message("停止控制")
    
    def emergency_stop(self):
        """紧急停止"""
        if self.dog:
            self.dog.vx = 0.0
            self.dog.vy = 0.0
            self.dog.wz = 0.0
            self.current_vx = 0.0
            self.current_vy = 0.0
            self.current_wz = 0.0
        self.log_message("🚨 紧急停止")
    
    def reset_posture(self):
        """重置姿态"""
        if self.dog:
            self.dog.vx = 0.0
            self.dog.vy = 0.0
            self.dog.wz = 0.0
            self.dog.body_height = 0.23
            self.current_vx = 0.0
            self.current_vy = 0.0
            self.current_wz = 0.0
            self.current_height = 0.23
            self.current_height_index = 2
            self.height_var.set(f"身高: {self.current_height:.2f} m")
        self.log_message("🔄 重置姿态")
    
    # 控制循环
    def control_loop(self):
        """主控制循环"""
        self.log_message(f"控制循环开始 - 模式: {self.current_mode}")
        last_status_time = 0
        
        while self.running and self.connected:
            try:
                vx, vy, wz = 0.0, 0.0, 0.0
                
                if self.current_mode == "键盘控制":
                    vx, vy, wz = self.calculate_keyboard_movement()
                elif self.current_mode == "手柄控制":
                    vx, vy, wz = self.get_movement_from_gamepad()
                    self.handle_gamepad_buttons()
                elif self.current_mode == "GUI按钮控制":
                    vx, vy, wz = self.calculate_gui_movement()
                
                # 更新机器狗
                if self.dog:
                    if (abs(vx - self.current_vx) > 0.01 or 
                        abs(vy - self.current_vy) > 0.01 or 
                        abs(wz - self.current_wz) > 0.01):
                        
                        self.current_vx = vx
                        self.current_vy = vy
                        self.current_wz = wz
                        
                        self.dog.vx = vx
                        self.dog.vy = vy
                        self.dog.wz = wz
                    
                    self.dog.body_height = self.current_height
                
                # 定期更新状态
                current_time = time.time()
                if current_time - last_status_time >= 1.0:
                    self.update_realtime_status(vx, vy, wz)
                    last_status_time = current_time
                
                time.sleep(0.05)  # 20Hz
                
            except Exception as e:
                self.log_message(f"控制错误: {e}")
                break
        
        self.log_message("控制循环结束")
    
    def calculate_keyboard_movement(self):
        """计算键盘移动"""
        vx, vy, wz = 0.0, 0.0, 0.0
        current_speed = self.speed_levels[self.current_speed_index]
        
        for key in self.pressed_keys:
            if key in self.movement_keys:
                move = self.movement_keys[key]
                vx += move['vx'] * current_speed
                vy += move['vy'] * current_speed
                wz += move['wz'] * self.max_turn_speed
        
        return vx, vy, wz
    
    def calculate_gui_movement(self):
        """计算GUI按钮移动"""
        vx, vy, wz = 0.0, 0.0, 0.0
        current_speed = self.speed_levels[self.current_speed_index]
        
        for key in self.gui_pressed_keys:
            if key in self.movement_keys:
                move = self.movement_keys[key]
                vx += move['vx'] * current_speed
                vy += move['vy'] * current_speed
                wz += move['wz'] * self.max_turn_speed
        
        return vx, vy, wz
    
    # UI更新方法
    def update_connection_indicator(self, connected):
        """更新连接指示器"""
        self.connection_indicator.delete("all")
        color = "green" if connected else "red"
        self.connection_indicator.create_oval(2, 2, 18, 18, fill=color, outline=color)
    
    def update_gamepad_indicator(self, connected):
        """更新手柄指示器"""
        self.gamepad_indicator.delete("all")
        color = "green" if connected else "red"
        self.gamepad_indicator.create_oval(2, 2, 13, 13, fill=color, outline=color)
    
    def update_keyboard_indicator(self, active):
        """更新键盘指示器"""
        self.keyboard_indicator.delete("all")
        color = "green" if active else "red"
        self.keyboard_indicator.create_oval(2, 2, 13, 13, fill=color, outline=color)
    
    def update_realtime_status(self, vx, vy, wz):
        """更新实时状态"""
        # 获取当前动作
        all_pressed = self.pressed_keys | self.gui_pressed_keys
        actions = []
        for key in all_pressed:
            if key in self.movement_keys:
                actions.append(self.movement_keys[key]['name'])
        
        action_text = ', '.join(actions) if actions else '静止'
        
        status_info = f"""[{time.strftime('%H:%M:%S')}] 实时状态:
  控制模式: {self.current_mode}
  当前动作: {action_text}
  速度: vx={vx:.2f} vy={vy:.2f} wz={wz:.2f}
  身高: {self.current_height:.2f}m ({self.current_height_index + 1}/5级)
  速度等级: {self.current_speed_index + 1}/6 ({self.speed_levels[self.current_speed_index]:.1f}m/s)
{'  手柄: ' + self.joystick.get_name() if self.gamepad_connected else '  手柄: 未连接'}
---"""
        
        self.message_queue.put(('realtime_status', status_info))
    
    def process_messages(self):
        """处理消息队列"""
        try:
            while True:
                msg_type, msg_data = self.message_queue.get_nowait()
                
                if msg_type == 'gamepad_status':
                    self.gamepad_status_label.configure(text=f"手柄: {msg_data}")
                    self.update_gamepad_indicator(self.gamepad_connected)
                    
                elif msg_type == 'realtime_status':
                    self.status_text.configure(state='normal')
                    current_content = self.status_text.get(1.0, 'end')
                    self.status_text.delete(1.0, 'end')
                    self.status_text.insert(1.0, msg_data + '\n' + current_content)
                    
                    lines = self.status_text.get(1.0, 'end').split('\n')
                    if len(lines) > 100:
                        self.status_text.delete(1.0, 'end')
                        self.status_text.insert(1.0, '\n'.join(lines[:100]))
                    
                    self.status_text.configure(state='disabled')
                    
        except queue.Empty:
            pass
        
        self.root.after(100, self.process_messages)
    
    def log_message(self, message):
        """记录消息"""
        current_time = time.strftime("%H:%M:%S")
        log_text = f"[{current_time}] {message}\n"
        
        self.status_text.configure(state='normal')
        self.status_text.insert('end', log_text)
        self.status_text.see('end')
        self.status_text.configure(state='disabled')
    
    def clear_log(self):
        """清空日志"""
        self.status_text.configure(state='normal')
        self.status_text.delete(1.0, 'end')
        self.status_text.configure(state='disabled')
    
    def on_closing(self):
        """窗口关闭事件"""
        self.stop_control()
        if self.connected:
            self.disconnect_from_dog()
        if self.keyboard_listener:
            self.stop_keyboard_listener()
        
        try:
            if self.pygame_initialized:
                pygame.quit()
        except:
            pass
            
        self.root.destroy()
    
    def run(self):
        """运行GUI"""
        # 创建按钮样式
        style = ttk.Style()
        style.configure('Pressed.TButton', background='lightblue')
        
        # 启动消息处理
        self.process_messages()
        
        # 初始状态检查
        self.root.after(100, self.initial_status_check)
        
        # 运行主循环
        self.root.mainloop()
    
    def initial_status_check(self):
        """初始状态检查"""
        self.log_message("🎮 机器狗统一控制中心已启动")
        
        if self.gamepad_connected:
            self.log_message(f"✓ 检测到手柄: {self.joystick.get_name()}")
        else:
            self.log_message("ℹ️ 未检测到游戏手柄，如需使用手柄请连接后点击'刷新手柄'")
            
        self.log_message("ℹ️ 请选择控制模式并连接机器狗后开始控制")

if __name__ == '__main__':
    try:
        app = RobodogUnifiedGUI()
        app.run()
    except Exception as e:
        print(f"程序启动失败: {e}")
        messagebox.showerror("启动失败", f"程序无法启动:\n{e}")
