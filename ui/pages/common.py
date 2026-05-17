from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout


def build_panel(title, content_layout):
    panel = QFrame()
    panel.setObjectName("Panel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(14, 12, 14, 14)
    layout.setSpacing(10)

    title_label = QLabel(title)
    title_label.setObjectName("PanelTitle")
    layout.addWidget(title_label)
    layout.addLayout(content_layout)
    return panel


def build_note(content):
    note = QLabel(content)
    note.setWordWrap(True)
    note.setObjectName("Note")
    return note
