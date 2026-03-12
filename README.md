#  🍽️ AI-Powered Restaurant Chatbot Assistant

An intelligent conversational assistant built with Python and NLP to automate customer interactions in restaurants — handling menu inquiries, order requests, and general questions through natural language.

---

## 📌 Overview

Traditional restaurant support relies heavily on manual staff interaction. This project replaces repetitive customer queries with an AI-driven chatbot that understands natural language, recognizes intent, and responds accurately in real time.

---

## ✨ Features

- 🧠 **Intent Recognition** — Understands what the customer is asking (menu, order, hours, etc.)
- 💬 **Natural Language Conversations** — Handles free-text input naturally
- 📋 **Menu Inquiry Handling** — Answers questions about dishes, ingredients, and availability
- 🛒 **Order Request Support** — Guides customers through the ordering process
- ⚡ **Automated Responses** — Reduces manual support load with instant replies

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python |
| NLP Framework | NLTK / spaCy |
| Intent Classification | Custom ML Model |
| Interface | CLI / Web (Flask) |

---

## 📁 Project Structure

```
restaurant-chatbot/
│
├── data/
│   ├── intents.json          # Training intents and responses
│   └── menu.json             # Restaurant menu data
│
├── model/
│   ├── train.py              # Model training script
│   └── chatbot_model.h5      # Saved trained model
│
├── src/
│   ├── chatbot.py            # Core chatbot logic
│   ├── preprocessing.py      # Text cleaning & tokenization
│   └── response_generator.py # Response selection logic
│
├── app.py                    # Main application entry point
├── requirements.txt
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites
```bash
Python 3.8+
pip
```

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/restaurant-chatbot.git
cd restaurant-chatbot

# Install dependencies
pip install -r requirements.txt

# Run the chatbot
python app.py
```

---

## 💡 How It Works

1. User inputs a message in natural language
2. Text is **preprocessed** (tokenized, lemmatized, cleaned)
3. **Intent classifier** predicts the category of the request
4. **Response generator** selects the most appropriate reply
5. Chatbot responds instantly to the user

---

## 📊 Results

- ✅ Reduced manual customer support interactions
- ✅ Faster response time compared to human-handled queries
- ✅ Accurate intent recognition across common restaurant scenarios

---

## 🙋‍♂️ Author

**Marwan Ashraf**
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-blue?logo=linkedin)](https://linkedin.com/in/your-profile)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-black?logo=github)](https://github.com/your-username)

---

## 📄 License

This project is licensed under the MIT License.
