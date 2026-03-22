# BIT-Events-Notifier 🚀

BIT-Events-Notifier is a Python-based tool that **notifies you via email about new events added to the BIP Portal (Activity Master)**. Stay up-to-date with all campus activities and never miss out on important events!

---

## 📝 Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

---

## 📚 Introduction

**BIT-Events-Notifier** is designed for students and faculty to automatically get notified about the latest events posted on the BIP Portal, directly in their inbox. It parses event data, tracks updates, and sends out timely notifications—perfect for staying informed without constantly checking the portal.

---

## ✨ Features

- 📧 **Email Notifications** for newly added events
- ⏳ **Automated Scheduling** to periodically check for new events
- 🗂️ **Event History Tracking** using JSON logs
- 🔒 **Environment Variable Support** via `.env` (for credentials, etc.)
- 🐍 **Easy-to-Run Python Script**

---

## ⚙️ Installation

1. **Clone the repository**
    ```bash
    git clone https://github.com/your-username/BIT-Events-Notifier.git
    cd BIT-Events-Notifier
    ```

2. **Install dependencies**
    ```bash
    pip install -r requirements.txt
    ```
    *(Make sure Python 3.7+ is installed)*

3. **Set up your environment variables**  
   Create a `.env` file in the project root and add your configuration (e.g., email credentials, database URI, etc.)  
   See `.env.example` for reference.

---

## 🚀 Usage

1. **Start the notifier**
    ```bash
    python app.py
    ```

2. **Logs & State**
    - Event logs are stored in `page1_logs.json`.
    - The latest checked event ID is tracked in `state.json`.

3. **Customize**
    - Adjust scheduling, notification logic, or email templates in `app.py` as needed.

---

## 🤝 Contributing

Contributions are welcome! To contribute:

1. **Fork** the repository
2. **Create a branch** (`git checkout -b feature/your-feature`)
3. **Commit your changes** (`git commit -am 'Add a feature'`)
4. **Push to the branch** (`git push origin feature/your-feature`)
5. **Open a Pull Request**

Please check existing issues or open a new one to discuss your ideas!

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

> **Maintained with ❤️ by the BIT-Events-Notifier Community**



## License
This project is licensed under the **MIT** License.

---
🔗 GitHub Repo: https://github.com/Tharanika-R-Git/BIT-Events-Notifier
