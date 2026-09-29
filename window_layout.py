"""Screen-aware sizing and scrollable content panels, without changing system DPI."""
import sys
import tkinter as tk
from tkinter import ttk


def window_dimensions(work_width, work_height):
    # Leave room for native window borders/title bar; work area already excludes taskbars.
    width = min(1160, max(1, work_width-48))
    height = min(840, max(1, work_height-96))
    return width, height, min(760, width), min(440, height)


def work_area(root):
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size',wintypes.DWORD),('monitor',wintypes.RECT),
                        ('work',wintypes.RECT),('flags',wintypes.DWORD)]
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.MonitorFromWindow.argtypes = [wintypes.HWND,wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        info = MonitorInfo(size=ctypes.sizeof(MonitorInfo))
        monitor = user32.MonitorFromWindow(root.winfo_id(),2)
        if monitor and user32.GetMonitorInfoW(monitor,ctypes.byref(info)):
            return info.work.left, info.work.top, info.work.right-info.work.left, info.work.bottom-info.work.top
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def fit_window(root):
    left,top,work_width,work_height = work_area(root)
    width,height,min_width,min_height = window_dimensions(work_width,work_height)
    root.geometry(f'{width}x{height}')
    root.minsize(min_width,min_height)
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.GetAncestor.argtypes = [wintypes.HWND,wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.SetWindowPos.argtypes = [wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,
                                        ctypes.c_int,ctypes.c_int,wintypes.UINT]
        user32.SetWindowPos.restype = wintypes.BOOL
        positioned = False
        def place_once(event):
            nonlocal positioned
            if event.widget is root and not positioned:
                # Native coordinates also handle monitors to the left of the primary
                # screen, where Tk's negative geometry offsets mean something else.
                handle = user32.GetAncestor(root.winfo_id(),2)
                positioned = bool(user32.SetWindowPos(handle,None,left+16,top+16,0,0,0x0015))
        root.bind('<Map>',place_once,add='+')
    else:
        root.geometry(f'{width}x{height}+{max(0,left+16)}+{max(0,top+16)}')


class ScrollableForm(ttk.Frame):
    def __init__(self, parent, *, stretch_height=False):
        super().__init__(parent)
        self.stretch_height = stretch_height
        self.columnconfigure(0,weight=1)
        self.rowconfigure(0,weight=1)
        self.canvas = tk.Canvas(self,width=320,height=1,highlightthickness=0,background='#f3f6fa')
        self.canvas.grid(row=0,column=0,sticky='nsew')
        vertical = ttk.Scrollbar(self,orient='vertical',command=self.canvas.yview)
        vertical.grid(row=0,column=1,sticky='ns')
        horizontal = ttk.Scrollbar(self,orient='horizontal',command=self.canvas.xview)
        horizontal.grid(row=1,column=0,sticky='ew')
        self.canvas.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.form = ttk.Frame(self.canvas,padding=(0,0,10,0))
        self.item = self.canvas.create_window(0,0,window=self.form,anchor='nw')
        self.form.bind('<Configure>',self._configure)
        self.canvas.bind('<Configure>',self._configure)
        root = self.winfo_toplevel()
        for sequence in ('<MouseWheel>','<Button-4>','<Button-5>'):
            root.bind(sequence,self._wheel,add='+')
        root.bind('<FocusIn>',self._focus,add='+')

    def _inside(self, widget):
        while widget is not None:
            if widget is self:
                return True
            widget = getattr(widget,'master',None)
        return False

    def _configure(self, _event=None):
        width = self.canvas.winfo_width() if self.stretch_height else max(self.canvas.winfo_width(),self.form.winfo_reqwidth())
        options = {'width': width}
        if self.stretch_height:
            options['height'] = max(self.canvas.winfo_height(),self.form.winfo_reqheight())
        self.canvas.itemconfigure(self.item,**options)
        self.canvas.configure(scrollregion=self.canvas.bbox(self.item))

    def _wheel(self, event):
        widget = self.winfo_containing(event.x_root,event.y_root)
        if widget is None or not self._inside(widget):
            return
        # Child controls own their wheel gestures; especially the chart's time-axis zoom.
        if widget.winfo_class() in ('TCombobox','Treeview','Text') or (widget.winfo_class()=='Canvas' and widget is not self.canvas):
            return
        if self.form.winfo_height() <= self.canvas.winfo_height():
            return
        delta = getattr(event,'delta',0)
        step = (-max(1,abs(delta)//120) if delta>0 else max(1,abs(delta)//120)) if delta else (-1 if event.num==4 else 1)
        self.canvas.yview_scroll(int(step),'units')
        return 'break'

    def _focus(self, event):
        widget = event.widget
        if not self._inside(widget) or widget.winfo_class() not in ('Entry','TEntry','Button','TButton','TCombobox'):
            return
        for axis in ('x','y'):
            position = getattr(widget,'winfo_root'+axis)()-getattr(self.form,'winfo_root'+axis)()
            length = widget.winfo_width() if axis=='x' else widget.winfo_height()
            visible = self.canvas.winfo_width() if axis=='x' else self.canvas.winfo_height()
            total = self.form.winfo_width() if axis=='x' else self.form.winfo_height()
            current = getattr(self.canvas,'canvas'+axis)(0)
            if position<current or position+length>current+visible:
                target = position if position<current else position+length-visible
                getattr(self.canvas,axis+'view_moveto')(max(0,target)/max(1,total))
