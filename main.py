import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# --- ОПРЕДЕЛЕНИЕ ПУТЕЙ ---
# Если программа запущена как скомпилированный .exe
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

IS_WINDOWS = os.name == "nt"
CRISPASR_PATH = BASE_DIR / "bin" / ("crispasr.exe" if IS_WINDOWS else "crispasr")
# Ты можешь поменять название модели, если скачаешь другую
MODEL_PATH = BASE_DIR / "models" / "parakeet-tdt-0.6b-v3-q8_0.gguf"


class TranscriptionThread(QThread):
    """Фоновый поток для обработки очереди файлов"""

    progress_update = pyqtSignal(int, str)  # Процент, Текст статуса
    log_update = pyqtSignal(str)  # Логи в консоль UI
    finished_queue = pyqtSignal()

    def __init__(self, file_queue, output_dir):
        super().__init__()
        self.file_queue = file_queue
        self.output_dir = Path(output_dir)

    def run(self):
        if not CRISPASR_PATH.exists():
            self.log_update.emit(
                f"❌ ОШИБКА: Движок не найден по пути:\n{CRISPASR_PATH}"
            )
            return
        if not MODEL_PATH.exists():
            self.log_update.emit(
                f"❌ ОШИБКА: Нейросеть не найдена!\nСкачайте GGUF модель и положите в:\n{MODEL_PATH}"
            )
            return

        total_files = len(self.file_queue)

        for index, file_path in enumerate(self.file_queue):
            file_path = Path(file_path)
            self.log_update.emit(f"\n▶️ Обработка: {file_path.name}...")
            self.progress_update.emit(
                int((index / total_files) * 100),
                f"Распознаю {index + 1} из {total_files}...",
            )

            # Настройки скрытия окна консоли для Windows
            startupinfo = None
            if IS_WINDOWS:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            cmd = [
                str(CRISPASR_PATH),
                "-m",
                str(MODEL_PATH),
                "-f",
                str(file_path),
                "--backend",
                "parakeet",
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    startupinfo=startupinfo,
                    encoding="utf-8",
                )

                if result.returncode == 0:
                    text = result.stdout.strip()
                    # Сохраняем результат в .txt файл
                    output_file = self.output_dir / f"{file_path.stem}.txt"
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(text)
                    self.log_update.emit(f"✅ Сохранено в: {output_file.name}")
                else:
                    self.log_update.emit(
                        f"❌ Ошибка в файле {file_path.name}:\n{result.stderr}"
                    )
            except Exception as e:
                self.log_update.emit(f"❌ Системная ошибка:\n{str(e)}")

        self.progress_update.emit(100, "Готово!")
        self.finished_queue.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Idus Transcriber Pro (Powered by Parakeet)")
        self.resize(800, 550)

        # --- ТЁМНАЯ ТЕМА ---
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; color: #cdd6f4; }
            QWidget { font-family: 'Segoe UI', Arial; font-size: 13px; }
            QLabel { color: #bac2de; }
            QPushButton {
                background-color: #89b4fa; color: #11111b;
                border-radius: 6px; padding: 8px; font-weight: bold;
            }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:disabled { background-color: #45475a; color: #7f849c; }
            QListWidget, QTextEdit {
                background-color: #181825; color: #cdd6f4;
                border: 1px solid #313244; border-radius: 6px; padding: 5px;
            }
            QProgressBar {
                border: 1px solid #313244; border-radius: 6px;
                text-align: center; color: white; background: #181825;
            }
            QProgressBar::chunk { background-color: #a6e3a1; border-radius: 5px; }
        """)

        # Главный Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # --- ВЕРХНЯЯ ПАНЕЛЬ (Очередь файлов) ---
        top_layout = QHBoxLayout()

        # Список файлов
        list_layout = QVBoxLayout()
        list_layout.addWidget(QLabel("Очередь аудиофайлов:"))
        self.file_list = QListWidget()
        list_layout.addWidget(self.file_list)

        # Кнопки управления списком
        btn_layout = QVBoxLayout()
        self.btn_add = QPushButton("+ Добавить аудио")
        self.btn_add.clicked.connect(self.add_files)
        self.btn_remove = QPushButton("- Удалить выделенное")
        self.btn_remove.clicked.connect(self.remove_file)
        self.btn_remove.setStyleSheet(
            "background-color: #f38ba8; color: #11111b;"
        )  # Красная кнопка

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_remove)
        btn_layout.addStretch()

        top_layout.addLayout(list_layout, stretch=3)
        top_layout.addLayout(btn_layout, stretch=1)
        layout.addLayout(top_layout, stretch=2)

        # --- СРЕДНЯЯ ПАНЕЛЬ (Папка вывода) ---
        mid_layout = QHBoxLayout()
        self.lbl_output = QLabel(f"Сохранять в: {Path.home()}")
        self.output_path = Path.home()
        self.btn_change_dir = QPushButton("Изменить папку")
        self.btn_change_dir.clicked.connect(self.change_output_dir)
        mid_layout.addWidget(self.lbl_output)
        mid_layout.addStretch()
        mid_layout.addWidget(self.btn_change_dir)
        layout.addLayout(mid_layout)

        # --- ПАНЕЛЬ ПРОГРЕССА И ЗАПУСКА ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_label = QLabel("Ожидание...")
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

        self.btn_start = QPushButton("🚀 НАЧАТЬ РАСПОЗНАВАНИЕ")
        self.btn_start.setMinimumHeight(40)
        self.btn_start.clicked.connect(self.start_transcription)
        layout.addWidget(self.btn_start)

        # --- ЛОГ КОНСОЛИ ---
        layout.addWidget(QLabel("Лог работы:"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Consolas", 10))
        layout.addWidget(self.log_output, stretch=2)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите аудио", "", "Audio (*.wav *.mp3 *.ogg *.flac)"
        )
        for f in files:
            # Проверяем, нет ли уже такого файла в списке
            items = [
                self.file_list.item(i).text() for i in range(self.file_list.count())
            ]
            if f not in items:
                self.file_list.addItem(f)

    def remove_file(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))

    def change_output_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Выберите папку для .txt файлов"
        )
        if directory:
            self.output_path = Path(directory)
            self.lbl_output.setText(f"Сохранять в: {self.output_path}")

    def start_transcription(self):
        files_to_process = [
            self.file_list.item(i).text() for i in range(self.file_list.count())
        ]

        if not files_to_process:
            QMessageBox.warning(self, "Пусто", "Добавьте аудиофайлы в очередь!")
            return

        # Блокируем интерфейс от случайных кликов
        self.btn_start.setEnabled(False)
        self.btn_add.setEnabled(False)
        self.btn_remove.setEnabled(False)
        self.btn_change_dir.setEnabled(False)
        self.log_output.clear()
        self.progress_bar.setValue(0)

        # Запускаем поток
        self.thread = TranscriptionThread(files_to_process, self.output_path)
        self.thread.progress_update.connect(self.update_progress)
        self.thread.log_update.connect(self.append_log)
        self.thread.finished_queue.connect(self.on_finished)
        self.thread.start()

    def update_progress(self, percent, text):
        self.progress_bar.setValue(percent)
        self.progress_label.setText(text)

    def append_log(self, text):
        self.log_output.append(text)

    def on_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_add.setEnabled(True)
        self.btn_remove.setEnabled(True)
        self.btn_change_dir.setEnabled(True)
        QMessageBox.information(self, "Успех", "Очередь файлов успешно обработана!")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
