# XTV Fileshare Bot - Franchisee Edition

![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)
![Database](https://img.shields.io/badge/MongoDB-Required-green?style=flat-square&logo=mongodb)
![Framework](https://img.shields.io/badge/Framework-Pyrogram-yellow?style=flat-square&logo=telegram)
![Status](https://img.shields.io/badge/Status-Active-success?style=flat-square)
![License](https://img.shields.io/badge/License-Proprietary-red?style=flat-square)
![Type](https://img.shields.io/badge/Type-Franchisee-orange?style=flat-square)

### Developed by **𝕏0L0™** (@davdxpx)

---

## 📖 Overview

This is the **Franchisee Version** of the **XTV Fileshare Bot**. It operates as a partner node within the larger XTV ecosystem. As a Franchisee, you run your own instance of the bot that connects to a central **Global Database (MainDB)** for content while maintaining your own **Local Database (PrivateDB)** for channel management and configurations.

**Key Differences in Franchisee Mode:**
*   **Global Content Access:** Your bot has Read-Only access to the massive global library of files.
*   **Local Control:** You have full control over your local channels, force subscriptions, and specific file bundles stored in your PrivateDB.
*   **Dual Rank System:** Users have a "Request Rank" (Global) and a "Fileshare Rank" (Local).
*   **Security:** Requires valid `FRANCHISEE_ID` and `FRANCHISEE_PASSWORD` to operate.

---

## ✨ Key Features

### 🌍 Global Integration
*   **Request Push:** Submit your local bundles to be added to the Global Library (MainDB).
*   **Series Channels:** Create automated local channels that update with new episodes/seasons from the global database.
*   **Dual Rank System:** Tracks user progress globally (Requests) and locally (File Sharing/Referrals).

### 📂 File Management
*   **Secure Storage:** Upload files to your private storage channel; the bot generates unique, protected links.
*   **Multi-File Bundles:** Group multiple files into a single access link.
*   **Smart Metadata:** Automatically fetches movie/TV show details (Posters, Ratings, Genres) from **TMDB**.

### 💰 Monetization & Growth
*   **Quest System:** Users must complete tasks (e.g., answer a quiz, visit a link) to access files.
*   **Premium Access:** Users can purchase "Premium" status to bypass Quests.
*   **Force Subscription:** Require users to join your specific local channels.
*   **Referral System:** Users earn XP and Premium rewards by inviting friends.

### 🛡️ Security
*   **Anti-Leech:** Automatically deletes sent files from the user's chat to prevent unauthorized sharing.
*   **CEO Security Check:** The bot verifies its integrity against the central CEO_ID.
*   **3-DB Architecture:** Separates Global (Read-Only), User (Shared), and Local (Private) data for maximum security.

---

## ⚙️ Prerequisites

To run the Franchisee version, you need:

1.  **Python 3.10+** installed.
2.  **Franchisee Credentials:** You **MUST** obtain a `FRANCHISEE_ID` and `FRANCHISEE_PASSWORD` from the CEO/Developer (@davdxpx).
3.  **MongoDB Databases:** You need 3 Connection URIs (can be same cluster, different DB names):
    *   `MAIN_URI` (Provided by CEO)
    *   `USER_URI` (Provided by CEO)
    *   `PRIVATE_URI` (Your local database)
4.  **Telegram API ID & Hash** (Get from [my.telegram.org](https://my.telegram.org)).
5.  **Bot Token** (Get from [@BotFather](https://t.me/BotFather)).
6.  **TMDB API Key** (Optional, for movie metadata).

---

## 🚀 Installation (Local)

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/yourusername/xtv-fileshare-franchisee.git
    cd xtv-fileshare-franchisee
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configuration:**
    Create a `.env` file in the root directory. You **must** include the Franchisee credentials.

    ```env
    # --- Telegram & Franchisee Identity ---
    API_ID=123456
    API_HASH=your_api_hash
    BOT_TOKEN=your_bot_token
    FRANCHISEE_ID=your_franchisee_id       # REQUIRED
    FRANCHISEE_PASSWORD=your_password      # REQUIRED

    # --- Database (3-DB Architecture) ---
    MAIN_URI=mongodb+srv://...             # Global Read-Only (Ask CEO)
    USER_URI=mongodb+srv://...             # Shared User Data (Ask CEO)
    PRIVATE_URI=mongodb+srv://...          # Your Local Data

    # --- Admins ---
    CEO_ID=123456789                       # The Main Owner ID
    ADMIN_IDS=123456789,987654321          # Comma-separated list of your admins

    # --- Integrations ---
    TMDB_API_KEY=your_tmdb_key
    ```

4.  **Run the Bot:**
    ```bash
    python main.py
    ```

---

## ☁️ Deployment (Railway)

**Railway** is recommended for hosting.

1.  **Fork this Repository** to your GitHub.
2.  **Create a New Project** on [Railway](https://railway.app/).
3.  **Deploy from GitHub repo** and select your fork.
4.  **Add Variables:**
    *   Go to the **Variables** tab.
    *   Add all variables from the [Configuration](#-configuration) section.
    *   **Crucial:** Ensure `FRANCHISEE_ID` and `FRANCHISEE_PASSWORD` are set correctly.
5.  **Start Command:** `python main.py`
6.  **Deploy:** Railway will build and run the bot.

---

## 🔧 Configuration Reference

| Variable | Description | Required |
| :--- | :--- | :--- |
| `API_ID` | Telegram API ID | ✅ Yes |
| `API_HASH` | Telegram API Hash | ✅ Yes |
| `BOT_TOKEN` | Bot Token | ✅ Yes |
| `FRANCHISEE_ID` | **Your Unique Franchise ID** | ✅ **YES** |
| `FRANCHISEE_PASSWORD` | **Your Franchise Password** | ✅ **YES** |
| `MAIN_URI` | Global Database Connection | ✅ Yes |
| `USER_URI` | User Database Connection | ✅ Yes |
| `PRIVATE_URI` | Local Database Connection | ✅ Yes |
| `CEO_ID` | Owner's ID (Security Check) | ✅ Yes |
| `ADMIN_IDS` | List of Admin IDs (comma-separated) | ✅ Yes |
| `TMDB_API_KEY` | TMDB API Key | ❌ Optional |

---

## 📞 Support

For Franchisee credentials, support, or bug reports, contact the developer:

*   **Developer:** [@davdxpx](https://t.me/davdxpx)
*   **Brand:** **𝕏0L0™**

---

<div align="center">
    <p>
        &copy; 2026 <strong>𝕏0L0™</strong>. All Rights Reserved.<br>
        <em>Developed with ❤️ by @davdxpx</em>
    </p>
</div>
