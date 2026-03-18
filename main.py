"""
Тонкий entrypoint: запуск UI.
Входной сценарий — через ModernJiraApp (customtkinter).
"""
from ui import ModernJiraApp


def main() -> None:
    app = ModernJiraApp()
    app.mainloop()


if __name__ == "__main__":
    main()
