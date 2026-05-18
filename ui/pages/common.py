from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout


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


def build_check_card(registry, title, detail="等待检查"):
    card = QFrame()
    card.setObjectName("ResultCard")
    card.setProperty("state", "pending")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)

    header = QHBoxLayout()
    title_label = QLabel(title)
    title_label.setObjectName("PanelLead")
    status_label = QLabel("未运行")
    status_label.setObjectName("StatusBadge")
    status_label.setProperty("state", "pending")
    header.addWidget(title_label)
    header.addStretch(1)
    header.addWidget(status_label)

    detail_label = QLabel(detail)
    detail_label.setObjectName("MutedText")
    detail_label.setWordWrap(True)
    detail_label.setMinimumHeight(42)
    detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

    layout.addLayout(header)
    layout.addWidget(detail_label)
    registry[title] = {
        "card": card,
        "status": status_label,
        "detail": detail_label,
    }
    return card
