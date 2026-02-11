# XTV Fileshare Bot

![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)
![Database](https://img.shields.io/badge/MongoDB-Required-green?style=flat-square&logo=mongodb)
![Framework](https://img.shields.io/badge/Framework-Pyrogram-yellow?style=flat-square&logo=telegram)
![Status](https://img.shields.io/badge/Status-Active-success?style=flat-square)
![License](https://img.shields.io/badge/License-Proprietary-red?style=flat-square)

### Developed by **𝕏0L0™** (@davdxpx)

---

## 📖 Overview

**XTV Fileshare Bot** is a professional, high-performance Telegram file-sharing solution designed for community growth and monetization. Built with **Python** and **Pyrogram**, it offers a robust system for storing files in private channels and generating secure, trackable access links.

Unlike standard file-sharing bots, XTV includes advanced features to boost engagement and revenue:
*   **Monetization:** Mandatory "Quest" system (Tasks/Quizzes) before file access.
*   **Growth:** Force Subscription to channels and Force Share requirements.
*   **Analytics:** Detailed admin dashboard with user growth and content performance stats.
*   **Anti-Leech:** Auto-delete files from user chats to prevent unauthorized sharing.

---

## ✨ Key Features

### 📂 File Management
*   **Secure Storage:** Upload files to a private storage channel; the bot generates unique, protected links.
*   **Multi-File Bundles:** Group multiple files (e.g., a full TV season) into a single access link.
*   **Smart Metadata:** Automatically fetches movie/TV show details (Posters, Ratings, Genres) from **TMDB**.

### 💰 Monetization & Growth
*   **Quest System:** Users must complete tasks (e.g., answer a quiz, visit a link) to access files.
*   **Premium Access:** Users can purchase "Premium" status to bypass Quests and Ads.
*   **Force Subscription:** Require users to join specific channels before using the bot.
*   **Referral System:** Users earn Premium rewards by inviting friends (Progress bar tracking included).
*   **Coupons & Daily Bonus:** Engage users with redeemable codes and daily activity rewards.

### 🛡️ Security & Performance
*   **Anti-Leech (Auto-Delete):** Automatically deletes sent files from the user's chat after a set time (e.g., 10 mins).
*   **Broadcasting:** Send mass messages to all users with detailed statistics.
*   **Async/Aiohttp:** Built for speed and high concurrency, handling thousands of requests efficiently.

---

## 🛠 Admin Panel

The bot features a comprehensive GUI-based Admin Panel accessible via `/admin`:

*   **📊 Stats:** View total users, active users (24h), new users, and top-performing bundles.
*   **⚙️ Settings:** Toggle Force Sub, Tasks, and Force Share on/off instantly.
*   **💰 Monetization:** Manage Premium users (Add/Remove/List).
*   **🚀 Growth:** Configure Referral targets, create Coupons, and manage Daily Bonuses.
*   **📦 Bundles:** Manage existing file bundles (Rename, Delete, View Stats).
*   **📢 Channels:** Add/Remove Force Sub and Storage channels directly from the bot.

---

## ⚙️ Prerequisites

Before you begin, ensure you have the following:

1.  **Python 3.10+** installed.
2.  **MongoDB Database** (local or cloud via MongoDB Atlas).
3.  **Telegram API ID & Hash** (Get from [my.telegram.org](https://my.telegram.org)).
4.  **Bot Token** (Get from [@BotFather](https://t.me/BotFather)).
5.  **TMDB API Key** (Optional, for movie metadata).

---

## 🚀 Installation (Local)

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/yourusername/xtv-fileshare-bot.git
    cd xtv-fileshare-bot
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configuration:**
    Create a `.env` file in the root directory and add your credentials:
    ```env
    API_ID=123456
    API_HASH=your_api_hash
    BOT_TOKEN=your_bot_token
    MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
    ADMIN_ID=123456789
    TMDB_API_KEY=your_tmdb_key
    ```

4.  **Run the Bot:**
    ```bash
    python main.py
    ```

---

## ☁️ Deployment (Railway)

**Railway** is the recommended platform for hosting this bot due to its ease of use and performance.

### Step-by-Step Guide:

1.  **Fork this Repository** to your own GitHub account.
2.  **Login to [Railway](https://railway.app/)** and create a "New Project".
3.  **Select "Deploy from GitHub repo"** and choose your forked repository.
4.  **Add Variables:**
    *   Go to the **Variables** tab in your Railway project.
    *   Add all the required environment variables (see the [Configuration](#-configuration) table below).
5.  **Start Command:**
    *   Railway should automatically detect the Python app.
    *   If asked for a Start Command, use: `python main.py`
6.  **Deploy:**
    *   Railway will build and deploy your bot. Check the "Logs" tab to confirm it's running.

> **Note:** If you need a database on Railway, you can add a **MongoDB** service within your project and use the provided `MONGO_URL` as your `MONGO_URI`.

---

## 🔧 Configuration

These variables can be set in your `.env` file or your hosting provider's environment variables settings.

| Variable | Description | Required |
| :--- | :--- | :--- |
| `API_ID` | Telegram API ID from my.telegram.org | ✅ Yes |
| `API_HASH` | Telegram API Hash from my.telegram.org | ✅ Yes |
| `BOT_TOKEN` | Bot Token from @BotFather | ✅ Yes |
| `MONGO_URI` | MongoDB Connection String | ✅ Yes |
| `ADMIN_ID` | Your Telegram User ID (for Admin Panel access) | ✅ Yes |
| `TMDB_API_KEY` | API Key from [themoviedb.org](https://www.themoviedb.org/) | ❌ Optional |

---

## 📞 Support

If you need assistance, encounter bugs, or want to purchase a license/custom version, please contact the developer directly:

*   **Developer:** [@davdxpx](https://t.me/davdxpx)
*   **Brand:** **𝕏0L0™**

---

<div align="center">
    <p>
        &copy; 2024 <strong>𝕏0L0™</strong>. All Rights Reserved.<br>
        <em>Developed with ❤️ by @davdxpx</em>
    </p>
</div>
