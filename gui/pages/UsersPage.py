"""Device user accounts: add, change level / password, delete (never the last administrator)."""

from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox
from gui.pages.DevicePage import DevicePage
from gui.pages.Forms import button, buttonRow, dataTable, fillTable, pageLayout, selectedRecord
from services.OnvifDevice import OnvifDevice

ADMINISTRATOR = "Administrator"
# Devices commonly require the password on SetUser as well, and cap it at 30 characters.
MAX_PASSWORD_LENGTH = 30


class UserDialog(QDialog):
    def __init__(self, parent, user=None):
        super().__init__(parent)
        self.setWindowTitle("Change user" if user else "Add user")
        form = QFormLayout(self)
        self.name = QLineEdit(user["username"] if user else "")
        self.name.setEnabled(user is None)
        self.password, self.again = QLineEdit(), QLineEdit()
        for edit in (self.password, self.again):
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.level = QComboBox()
        self.level.addItems(OnvifDevice.LEVELS)
        if user:
            self.level.setCurrentText(user["level"])
        form.addRow("Username", self.name)
        form.addRow("Password", self.password)
        form.addRow("Confirm password", self.again)
        form.addRow("Level", self.level)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def problem(self):
        if not self.name.text().strip() or not self.password.text():
            return "Username and password are required."
        if self.password.text() != self.again.text():
            return "Passwords do not match."
        if len(self.password.text()) > MAX_PASSWORD_LENGTH:
            return "Use at most 30 characters."
        return ""

    def accept(self):
        message = self.problem()
        if message:
            QMessageBox.warning(self, "Warning", message)
            return
        super().accept()

    def values(self):
        return self.name.text().strip(), self.password.text(), self.level.currentText()


class UsersPage(DevicePage):
    ICON = "users"
    TITLE = "Users"

    def __init__(self, workspace):
        super().__init__(workspace)
        self.users = []
        layout = pageLayout(self)
        self.table = dataTable(2)
        layout.addWidget(self.table, 1)
        buttonRow(
            layout,
            button("Add user", self.add, primary=True),
            button("Change", self.change),
            button("Delete", self.delete),
        )

    def load(self, profile):
        self.run(self.device.users, self.show)

    def show(self, users):
        self.users = users
        self.table.setHorizontalHeaderLabels(["Username", "Level"])
        fillTable(self.table, users, lambda user: (user["username"], user["level"]), centered=(1,))
        self.present()
        self.workspace.loaded()

    def ask(self, user=None):
        dialog = UserDialog(self, user)
        return dialog.values() if dialog.exec() else None

    def plaintextWarning(self):
        if self.device.session.config.onvifHttps:
            return []
        return ["WARNING: ONVIF sends this password unencrypted over HTTP. Enable Settings › ONVIF HTTPS to protect it."]

    def isSessionAccount(self, user):
        return user["username"] == self.device.session.config.username

    def add(self):
        values = self.ask()
        if values and self.workspace.confirm("Add user", [f"{values[0]} ({values[2]})"] + self.plaintextWarning()):
            self.run(lambda: self.device.createUser(*values), lambda _: self.load(None), "Saving…")

    def change(self):
        user = selectedRecord(self.table)
        values = self.ask(user) if user else None
        if not values:
            return
        lines = [f"{user['username']}: {user['level']} → {values[2]}", "Password is replaced."]
        if self.isSessionAccount(user):
            lines.append("This is the account the app is using: update the login afterwards.")
        if self.workspace.confirm("Change user", lines + self.plaintextWarning()):
            self.run(lambda: self.device.setUser(*values), lambda _: self.load(None), "Saving…")

    def delete(self):
        user = selectedRecord(self.table)
        if not user:
            return
        administrators = [u for u in self.users if u["level"] == ADMINISTRATOR]
        if user["level"] == ADMINISTRATOR and len(administrators) <= 1:
            self.workspace.warn("Refusing to delete the last administrator.")
            return
        lines = [f"Delete user {user['username']} ({user['level']})?"]
        if self.isSessionAccount(user):
            lines.append("This is the account the app is using; the session will lose access.")
        if self.workspace.confirm("Delete user", lines):
            self.run(lambda: self.device.deleteUser(user["username"]), lambda _: self.load(None), "Deleting…")
