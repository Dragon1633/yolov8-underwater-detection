import os
import shutil
from datetime import datetime, timedelta
from PyQt5.QtCore import QThread, pyqtSignal, QTimer

from src.utils.general import get_param

class CleanupThread(QThread):

    def __init__(self, base_path, parent=None):
        super().__init__(parent)
        self.base_path = base_path  # 需清理的根目录
        self.retain_days = get_param("save picture days")
        print("图片保留天数：", self.retain_days)
        self._is_running = True

    def run(self):
        """线程主任务：定期清理过期文件夹"""
        while self._is_running:
            try:
                self.cleanup_folders()
                # 每天执行一次（86400秒），避免频繁占用资源
                self.sleep(86400)
            except Exception as e:
                # self.log_signal.emit(f"清理出错: {str(e)}")
                print(f"floder_clean_up清理出错: {str(e)}")
                self.sleep(3600)  # 出错后等待1小时再试

    def stop(self):
        """停止线程"""
        self._is_running = False

    def cleanup_folders(self):
        """清理过期文件夹"""
        now = datetime.now()
        # 计算保留日期（当前日期 - 保留天数）
        retain_date = (now - timedelta(days=self.retain_days)).date()

        try:
            # 遍历根目录下的所有文件夹
            for folder_name in os.listdir(self.base_path):
                folder_path = os.path.join(self.base_path, folder_name)

                # 文件夹名称格式为 "YYYY-MM-DD" 或类似
                try:
                    # 解析文件夹名中的日期（如 "2024-07-12"）
                    folder_date = datetime.strptime(folder_name, "%Y-%m-%d").date()
                    print(f"正在检查文件夹: {folder_path}, 日期: {folder_date}")
                    if folder_date < retain_date:
                        shutil.rmtree(folder_path)  # 递归删除文件夹
                        print(f"已删除过期文件夹: {folder_path}")
                    else:
                        print("保留日期未到，跳过删除: ", folder_path)
                        break           # 如果日期大于保留日期，则不再继续检查后续文件夹
                except ValueError:
                    # 文件夹名不符合日期格式，跳过
                    continue
        except Exception as e:
            print(f"floder_clean_up遍历文件夹出错: {str(e)}")