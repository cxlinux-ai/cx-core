//! Chat history and message types

use chrono::{DateTime, Utc};

/// Role in a chat conversation
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChatRole {
    /// System message (instructions)
    System,
    /// User message
    User,
    /// AI assistant response
    Assistant,
}

/// A single chat message
#[derive(Debug, Clone)]
pub struct ChatMessage {
    pub role: ChatRole,
    pub content: String,
    pub timestamp: DateTime<Utc>,
}

impl ChatMessage {
    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: ChatRole::User,
            content: content.into(),
            timestamp: Utc::now(),
        }
    }

    pub fn assistant(content: impl Into<String>) -> Self {
        Self {
            role: ChatRole::Assistant,
            content: content.into(),
            timestamp: Utc::now(),
        }
    }

    pub fn system(content: impl Into<String>) -> Self {
        Self {
            role: ChatRole::System,
            content: content.into(),
            timestamp: Utc::now(),
        }
    }
}

/// Chat history manager
#[derive(Debug, Clone)]
pub struct ChatHistory {
    messages: Vec<ChatMessage>,
    max_messages: usize,
}

impl ChatHistory {
    pub fn new() -> Self {
        Self {
            messages: Vec::new(),
            max_messages: 100,
        }
    }

    pub fn with_capacity(max_messages: usize) -> Self {
        Self {
            messages: Vec::with_capacity(max_messages),
            max_messages,
        }
    }

    /// Add a message to history
    pub fn add(&mut self, message: ChatMessage) {
        self.messages.push(message);

        // Trim old messages if needed
        while self.messages.len() > self.max_messages {
            // Keep system messages, remove oldest non-system
            if let Some(pos) = self
                .messages
                .iter()
                .position(|m| m.role != ChatRole::System)
            {
                self.messages.remove(pos);
            } else {
                break;
            }
        }
    }

    /// Clear all messages
    pub fn clear(&mut self) {
        self.messages.clear();
    }

    /// Get all messages
    pub fn messages(&self) -> &[ChatMessage] {
        &self.messages
    }

    /// Get messages for API request (exclude system, format for provider)
    pub fn for_api(&self) -> Vec<&ChatMessage> {
        self.messages.iter().collect()
    }

    /// Get last N messages
    pub fn last(&self, n: usize) -> &[ChatMessage] {
        let start = self.messages.len().saturating_sub(n);
        &self.messages[start..]
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.messages.is_empty()
    }

    /// Get message count
    pub fn len(&self) -> usize {
        self.messages.len()
    }

    /// Get last user message
    pub fn last_user_message(&self) -> Option<&ChatMessage> {
        self.messages
            .iter()
            .rev()
            .find(|m| m.role == ChatRole::User)
    }

    /// Get last assistant message
    pub fn last_assistant_message(&self) -> Option<&ChatMessage> {
        self.messages
            .iter()
            .rev()
            .find(|m| m.role == ChatRole::Assistant)
    }
}

impl Default for ChatHistory {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_chat_history() {
        let mut history = ChatHistory::new();

        history.add(ChatMessage::user("Hello"));
        history.add(ChatMessage::assistant("Hi there!"));

        assert_eq!(history.len(), 2);
        assert_eq!(history.last_user_message().unwrap().content, "Hello");
        assert_eq!(
            history.last_assistant_message().unwrap().content,
            "Hi there!"
        );
    }

    #[test]
    fn test_history_capacity() {
        let mut history = ChatHistory::with_capacity(3);

        history.add(ChatMessage::user("1"));
        history.add(ChatMessage::assistant("2"));
        history.add(ChatMessage::user("3"));
        history.add(ChatMessage::assistant("4"));

        assert_eq!(history.len(), 3);
    }
}
