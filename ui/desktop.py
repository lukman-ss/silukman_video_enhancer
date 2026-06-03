"""PySide6 desktop shell for silukman_video_enhancer."""

from __future__ import annotations

import sys
from pathlib import Path

from app.config import EnhancementConfig
from app.workers import BatchCancelToken, PipelineNotImplementedError, run_batch_jobs, run_desktop_job
from ui.desktop_queue import (
    DesktopEtaTracker,
    DesktopQueueModel,
    OUTPUT_FORMATS,
    VIDEO_EXTENSIONS,
    default_batch_output_path,
    with_output_format,
)
from ui.desktop_state import DesktopSettings, DesktopSettingsStore

try:
    from PySide6.QtCore import QObject, QThread, Qt, QUrl, Signal
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QProgressBar,
        QSpinBox,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised only without PySide6
    raise SystemExit(
        "PySide6 is required for the desktop app. Install dependencies with "
        "`pip install -r requirements.txt`."
    ) from exc


class EnhancementWorker(QObject):
    progress = Signal(int, str)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, config: EnhancementConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        try:
            run_desktop_job(self.config, self.progress.emit)
        except PipelineNotImplementedError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            self.failed.emit(f"Unexpected worker error: {exc}")
        finally:
            self.finished.emit()


class BatchEnhancementWorker(QObject):
    progress = Signal(int, str)
    file_progress = Signal(int, int, str, str)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, configs: list[EnhancementConfig], cancel_token: BatchCancelToken) -> None:
        super().__init__()
        self.configs = configs
        self.cancel_token = cancel_token

    def run(self) -> None:
        try:
            run_batch_jobs(
                self.configs,
                self._emit_file_progress,
                stop_flag=self.cancel_token.is_cancelled,
            )
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            self.failed.emit(f"Unexpected batch worker error: {exc}")
        finally:
            self.finished.emit()

    def _emit_file_progress(self, file_index: int, file_total: int, percent: int, message: str) -> None:
        if file_index < len(self.configs):
            status = "Done" if percent >= 100 and "Done:" in message else "Processing"
            if "Error:" in message:
                status = "Error"
            if "Cancelled" in message:
                status = "Error"
            self.file_progress.emit(file_index, percent, status, message)
        overall = round(((file_index + (percent / 100)) / max(1, file_total)) * 100)
        self.progress.emit(min(100, max(0, overall)), message)


class VideoPathEdit(QLineEdit):
    """Input field that accepts dragged local video files."""

    video_extensions = VIDEO_EXTENSIONS

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # pragma: no cover - Qt event boundary
        if self._supported_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # pragma: no cover - Qt event boundary
        paths = self._supported_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        self.setText(str(paths[0]))
        parent = self.window()
        if hasattr(parent, "_add_input_files"):
            parent._add_input_files(paths)
        elif hasattr(parent, "_set_default_output_from_input"):
            parent._set_default_output_from_input(paths[0])
        event.acceptProposedAction()

    @classmethod
    def _supported_paths(cls, mime_data) -> list[Path]:
        paths = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.suffix.lower() in cls.video_extensions:
                paths.append(path)
        return paths


class QueueTableWidget(QTableWidget):
    rows_reordered = Signal()

    def dropEvent(self, event) -> None:  # pragma: no cover - Qt event boundary
        super().dropEvent(event)
        self.rows_reordered.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("silukman_video_enhancer")
        self.resize(1100, 720)
        self._thread: QThread | None = None
        self._worker: EnhancementWorker | BatchEnhancementWorker | None = None
        self._cancel_token: BatchCancelToken | None = None
        self.queue_model = DesktopQueueModel()
        self.eta_tracker = DesktopEtaTracker()
        self.settings_store = DesktopSettingsStore(Path.home() / ".silukman_video_enhancer" / "desktop_settings.json")

        self.input_edit = VideoPathEdit()
        self.input_edit.setPlaceholderText("Select or drop a video file")
        self.output_edit = QLineEdit("output.mp4")
        self.model_box = QComboBox()
        self.model_box.addItems(["realesrgan", "swinir", "srcnn"])
        self.recent_box = QComboBox()
        self.recent_box.addItem("Recent files")
        self.output_format_box = QComboBox()
        self.output_format_box.addItems(list(OUTPUT_FORMATS))
        self.scale_box = QComboBox()
        self.scale_box.addItems(["1", "2", "4"])
        self.scale_box.setCurrentText("2")
        self.device_box = QComboBox()
        self.device_box.addItems(["auto", "cpu", "cuda", "coreml", "directml"])
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(18)
        self.denoise_check = QCheckBox("Denoise")
        self.color_check = QCheckBox("Color correct")
        self.start_button = QPushButton("Start Enhancement")
        self.add_files_button = QPushButton("Add Files")
        self.remove_files_button = QPushButton("Remove Selected")
        self.retry_failed_button = QPushButton("Retry Failed")
        self.open_file_button = QPushButton("Open File")
        self.open_folder_button = QPushButton("Open Output Folder")
        self.cancel_button = QPushButton("Cancel Batch")
        self.cancel_button.setEnabled(False)
        self.retry_failed_button.setEnabled(False)
        self.open_file_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self.queue_table = QueueTableWidget(0, 5)
        self.queue_table.setHorizontalHeaderLabels(["Input", "Output", "Status", "Progress", "Message"])
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue_table.setDragDropMode(QAbstractItemView.InternalMove)
        self.queue_table.setDragDropOverwriteMode(False)
        self.queue_table.rows_reordered.connect(self._sync_queue_model_from_table_order)
        self.progress_bar = QProgressBar()
        self.eta_label = QLabel("ETA --:--")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)

        self._build_layout()
        self._load_settings()

    def _build_layout(self) -> None:
        root = QWidget()
        layout = QGridLayout(root)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(0, 1)
        layout.setRowStretch(1, 0)

        layout.addWidget(self._build_settings_panel(), 0, 0)
        layout.addWidget(self._build_preview_panel(), 0, 1)
        layout.addWidget(self._build_progress_panel(), 1, 0, 1, 2)
        self.setCentralWidget(root)

    def _build_settings_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(340)
        layout = QVBoxLayout(panel)

        input_button = QPushButton("Browse Input")
        input_button.clicked.connect(self._select_input)
        self.add_files_button.clicked.connect(self._select_batch_inputs)
        self.remove_files_button.clicked.connect(self._remove_selected_files)
        self.retry_failed_button.clicked.connect(self._retry_failed_files)
        self.open_file_button.clicked.connect(self._open_selected_output_file)
        self.open_folder_button.clicked.connect(self._open_selected_output_folder)
        output_button = QPushButton("Choose Output")
        output_button.clicked.connect(self._select_output)

        form = QFormLayout()
        form.addRow("Input", self.input_edit)
        form.addRow("", input_button)
        form.addRow("Recent", self.recent_box)
        form.addRow("Output", self.output_edit)
        form.addRow("", output_button)
        form.addRow("Format", self.output_format_box)
        form.addRow("Model", self.model_box)
        form.addRow("Scale", self.scale_box)
        form.addRow("Device", self.device_box)
        form.addRow("CRF", self.crf_spin)
        form.addRow("Filters", self.denoise_check)
        form.addRow("", self.color_check)

        layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(self.queue_table)
        queue_buttons = QHBoxLayout()
        queue_buttons.addWidget(self.add_files_button)
        queue_buttons.addWidget(self.remove_files_button)
        queue_buttons.addWidget(self.retry_failed_button)
        layout.addLayout(queue_buttons)
        layout.addWidget(self.start_button)
        layout.addWidget(self.cancel_button)
        self.start_button.clicked.connect(self._start_job)
        self.cancel_button.clicked.connect(self._cancel_batch)
        self.recent_box.currentIndexChanged.connect(self._add_recent_selection)
        self.output_format_box.currentTextChanged.connect(self._set_output_format)
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.addWidget(self._preview_frame("Original"))
        layout.addWidget(self._preview_frame("Enhanced"))
        return panel

    def _preview_frame(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setMinimumSize(320, 240)
        layout = QVBoxLayout(frame)
        label = QLabel(title)
        label.setStyleSheet("font-weight: 600;")
        placeholder = QLabel("Preview will use sampled frames in a later phase.")
        placeholder.setWordWrap(True)
        placeholder.setStyleSheet("color: #666;")
        layout.addWidget(label)
        layout.addStretch(1)
        layout.addWidget(placeholder)
        layout.addStretch(1)
        return frame

    def _build_progress_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.eta_label)
        actions = QHBoxLayout()
        actions.addWidget(self.open_file_button)
        actions.addWidget(self.open_folder_button)
        layout.addLayout(actions)
        layout.addWidget(self.log_view)
        return panel

    def _select_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select input video",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi);;All Files (*)",
        )
        if path:
            self.input_edit.setText(path)
            self._add_input_files([Path(path)])
            if self.output_edit.text() == "output.mp4":
                self._set_default_output_from_input(Path(path))

    def _select_batch_inputs(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add videos to queue",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v);;All Files (*)",
        )
        if paths:
            self._add_input_files([Path(path) for path in paths])

    def _remove_selected_files(self) -> None:
        rows = [index.row() for index in self.queue_table.selectedIndexes()]
        if not rows:
            return
        self.queue_model.remove_many(rows)
        self._refresh_queue_table()

    def _retry_failed_files(self) -> None:
        retried = self.queue_model.retry_failed()
        if retried:
            self.log_view.append(f"Retry queued: {len(retried)} file(s)")
            self.retry_failed_button.setEnabled(False)
            self._refresh_queue_table()

    def _add_input_files(self, paths: list[Path]) -> None:
        added = self.queue_model.add_files(paths, self.output_format_box.currentText())
        if added:
            self.settings_store.remember_files([item.input_path for item in added])
            self._refresh_recent_files()
            self._refresh_queue_table()
            if len(self.queue_model) == 1:
                first = self.queue_model.items()[0]
                self.input_edit.setText(str(first.input_path))
                self._set_default_output_from_input(first.input_path)

    def _refresh_queue_table(self) -> None:
        items = self.queue_model.items()
        self.queue_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [
                (0, item.input_path.name),
                (1, str(item.output_path)),
                (2, item.status),
                (4, item.message),
            ]
            for column, value in values:
                table_item = QTableWidgetItem(value)
                if column == 0:
                    table_item.setData(Qt.UserRole, str(item.input_path))
                self.queue_table.setItem(row, column, table_item)
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(item.progress)
            progress.setFormat(f"{item.progress}%")
            self.queue_table.setCellWidget(row, 3, progress)
        self.retry_failed_button.setEnabled(bool(self.queue_model.failed_items()))

    def _sync_queue_model_from_table_order(self) -> None:
        input_paths: list[Path] = []
        for row in range(self.queue_table.rowCount()):
            table_item = self.queue_table.item(row, 0)
            if table_item is None:
                continue
            value = table_item.data(Qt.UserRole) or table_item.text()
            input_paths.append(Path(value))
        self.queue_model.reorder_by_input_paths(input_paths)
        self._refresh_queue_table()

    def _base_config_from_ui(self) -> EnhancementConfig:
        input_text = self.input_edit.text() or "input.mp4"
        return EnhancementConfig(
            input_path=Path(input_text).expanduser(),
            output_path=Path(self.output_edit.text()).expanduser(),
            model=self.model_box.currentText(),
            scale=int(self.scale_box.currentText()),
            device=self.device_box.currentText(),
            crf=self.crf_spin.value(),
            denoise=self.denoise_check.isChecked(),
            color_correct=self.color_check.isChecked(),
        )

    def _settings_from_ui(self) -> DesktopSettings:
        return DesktopSettings(
            model=self.model_box.currentText(),
            scale=int(self.scale_box.currentText()),
            device=self.device_box.currentText(),
            crf=self.crf_spin.value(),
            denoise=self.denoise_check.isChecked(),
            color_correct=self.color_check.isChecked(),
            recent_files=self.settings_store.load().recent_files,
        )

    def _load_settings(self) -> None:
        settings = self.settings_store.load()
        self.model_box.setCurrentText(settings.model)
        self.scale_box.setCurrentText(str(settings.scale))
        self.device_box.setCurrentText(settings.device)
        self.crf_spin.setValue(settings.crf)
        self.denoise_check.setChecked(settings.denoise)
        self.color_check.setChecked(settings.color_correct)
        self._refresh_recent_files(settings)

    def _save_settings(self) -> None:
        self.settings_store.save(self._settings_from_ui())

    def _refresh_recent_files(self, settings: DesktopSettings | None = None) -> None:
        active = settings or self.settings_store.load()
        self.recent_box.blockSignals(True)
        self.recent_box.clear()
        self.recent_box.addItem("Recent files")
        for path in active.recent_files:
            self.recent_box.addItem(Path(path).name, path)
        self.recent_box.blockSignals(False)

    def _add_recent_selection(self, index: int) -> None:
        if index <= 0:
            return
        path = self.recent_box.itemData(index)
        if path:
            self._add_input_files([Path(path)])
        self.recent_box.setCurrentIndex(0)

    def _set_default_output_from_input(self, source: Path) -> None:
        if self.output_edit.text() == "output.mp4" or not self.output_edit.text().strip():
            self.output_edit.setText(str(default_batch_output_path(source, self.output_format_box.currentText())))

    def _set_output_format(self, extension: str) -> None:
        self.queue_model.set_all_output_format(extension)
        output_text = self.output_edit.text().strip()
        if output_text:
            self.output_edit.setText(str(with_output_format(Path(output_text), extension)))
        else:
            source = Path(self.input_edit.text() or "output.mp4")
            self.output_edit.setText(str(default_batch_output_path(source, extension)))
        self._refresh_queue_table()

    def _select_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose output video",
            self.output_edit.text(),
            "MP4 Video (*.mp4);;Matroska Video (*.mkv);;MOV Video (*.mov);;All Files (*)",
        )
        if path:
            self.output_edit.setText(path)
            suffix = Path(path).suffix.lower()
            if suffix in OUTPUT_FORMATS:
                self.output_format_box.setCurrentText(suffix)

    def _config_from_ui(self) -> EnhancementConfig:
        return self._base_config_from_ui()

    def _start_job(self) -> None:
        try:
            configs = self._queue_configs_from_ui()
            for config in configs:
                config.validate(require_existing_input=True)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return

        if len(configs) == 1:
            self.log_view.append(f"Starting: {configs[0].summary()}")
        else:
            self.log_view.append(f"Starting batch: {len(configs)} files")
        self._save_settings()
        self.progress_bar.setValue(0)
        self.eta_tracker.reset()
        self.eta_label.setText("ETA calculating...")
        self.start_button.setEnabled(False)
        self.open_file_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)

        self._thread = QThread()
        if len(configs) == 1:
            self._worker = EnhancementWorker(configs[0])
            self._worker.progress.connect(self._on_progress)
        else:
            self._cancel_token = BatchCancelToken()
            self._worker = BatchEnhancementWorker(configs, self._cancel_token)
            self._worker.progress.connect(self._on_progress)
            self._worker.file_progress.connect(self._on_file_progress)
            self.cancel_button.setEnabled(True)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.failed.connect(self._on_failure)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _queue_configs_from_ui(self) -> list[EnhancementConfig]:
        if len(self.queue_model) == 0:
            config = self._config_from_ui()
            return [config]
        return self.queue_model.configs_from_base(self._base_config_from_ui())

    def _on_progress(self, progress: int, message: str) -> None:
        self.progress_bar.setValue(progress)
        self.eta_label.setText(self.eta_tracker.label(progress))
        self.log_view.append(message)

    def _on_failure(self, message: str) -> None:
        self.log_view.append(message)

    def _on_file_progress(self, row: int, percent: int, status: str, message: str) -> None:
        if row < len(self.queue_model):
            self.queue_model.update(row, status=status, progress=percent, message=message)
            self._refresh_queue_table()
            if status == "Done":
                self.open_file_button.setEnabled(True)
                self.open_folder_button.setEnabled(True)

    def _cancel_batch(self) -> None:
        if self._cancel_token is not None:
            self._cancel_token.cancel()
            self.log_view.append("Batch cancellation requested.")
            self.cancel_button.setEnabled(False)

    def _on_worker_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._worker = None
        self._cancel_token = None
        self.open_file_button.setEnabled(any(item.status == "Done" for item in self.queue_model.items()))
        self.open_folder_button.setEnabled(any(item.status == "Done" for item in self.queue_model.items()))

    def _selected_or_last_done_item(self):
        rows = [index.row() for index in self.queue_table.selectedIndexes()]
        items = self.queue_model.items()
        for row in rows:
            if row < len(items):
                return items[row]
        done = [item for item in items if item.status == "Done"]
        return done[-1] if done else None

    def _open_selected_output_file(self) -> None:
        item = self._selected_or_last_done_item()
        if item is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.output_path)))

    def _open_selected_output_folder(self) -> None:
        item = self._selected_or_last_done_item()
        if item is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(item.output_path.parent)))

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
