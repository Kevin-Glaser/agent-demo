import os
import threading
from typing import Callable, List, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent


class SkillFileHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[], None], debounce_ms: int = 500):
        super().__init__()
        self.callback = callback
        self.debounce_ms = debounce_ms
        self._timer: Optional[threading.Timer] = None
        self._changed_files = set()
    
    def on_modified(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if event.src_path.endswith('SKILL.md') or event.src_path.endswith('.zip'):
            self._schedule_reload(event.src_path)
    
    def on_created(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if event.src_path.endswith('SKILL.md') or event.src_path.endswith('.zip'):
            self._schedule_reload(event.src_path)
    
    def on_deleted(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if event.src_path.endswith('SKILL.md') or event.src_path.endswith('.zip'):
            self._schedule_reload(event.src_path)
    
    def _schedule_reload(self, file_path: str):
        self._changed_files.add(file_path)
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(self.debounce_ms / 1000.0, self._trigger_reload)
        self._timer.start()
    
    def _trigger_reload(self):
        if self._changed_files:
            print(f"Skill files changed: {self._changed_files}")
            self.callback()
            self._changed_files.clear()


class SkillWatcher:
    def __init__(self, directories: List[str], callback: Callable[[], None], debounce_ms: int = 500):
        self.directories = directories
        self.callback = callback
        self.debounce_ms = debounce_ms
        self.observer: Optional[Observer] = None
        self.handler = SkillFileHandler(callback, debounce_ms)
    
    def _get_watch_paths(self) -> List[str]:
        paths = []
        for directory in self.directories:
            if os.path.exists(directory):
                paths.append(directory)
        return paths
    
    def start(self):
        if self.observer:
            self.stop()
        
        self.observer = Observer()
        watch_paths = self._get_watch_paths()
        
        for path in watch_paths:
            self.observer.schedule(self.handler, path, recursive=True)
            print(f"Watching for skill changes in: {path}")
        
        if watch_paths:
            self.observer.start()
            print("Skill file watcher started")
    
    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            print("Skill file watcher stopped")
    
    def update_directories(self, directories: List[str]):
        self.directories = directories
        if self.observer:
            self.stop()
            self.start()