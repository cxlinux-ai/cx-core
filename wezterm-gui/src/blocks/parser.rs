//! OSC Sequence Parser for CX Terminal block markers

use super::markers;

/// Parsed CX Terminal OSC sequence
#[derive(Debug, Clone)]
pub enum CXSequence {
    /// Block started: command, timestamp
    BlockStart { command: String, timestamp: i64 },

    /// Block ended: exit code, timestamp
    BlockEnd { exit_code: i32, timestamp: i64 },

    /// Prompt started
    PromptStart,

    /// Prompt ended
    PromptEnd,

    /// Current working directory changed
    CwdChanged { path: String },

    /// AI request: explain
    AIExplain { text: String },

    /// AI request: suggest
    AISuggest { query: String },

    /// Agent request
    AgentRequest { name: String, command: String },

    /// Feature flags
    Features {
        blocks: bool,
        ai: bool,
        agents: bool,
    },

    /// Unknown/unrecognized sequence
    Unknown(String),
}

/// Parser for CX Terminal OSC sequences
pub struct BlockParser;

impl BlockParser {
    /// Parse a CX Terminal OSC sequence
    /// Input format: "777;cx;type;key=value;key=value..."
    pub fn parse(osc_data: &str) -> Option<CXSequence> {
        // Check for CX prefix
        if !osc_data.starts_with("777;cx;") {
            return None;
        }

        let data = &osc_data[7..]; // Skip "777;cx;"
        let parts: Vec<&str> = data.split(';').collect();

        if parts.is_empty() {
            return None;
        }

        let seq_type = parts[0];
        let params = Self::parse_params(&parts[1..]);

        match seq_type {
            "block" => Self::parse_block(&params),
            "prompt" => Self::parse_prompt(&params),
            "cwd" => Self::parse_cwd(&params),
            "ai" => Self::parse_ai(&params),
            "agent" => Self::parse_agent(&params),
            "features" => Self::parse_features(&params),
            _ => Some(CXSequence::Unknown(osc_data.to_string())),
        }
    }

    fn parse_params(parts: &[&str]) -> std::collections::HashMap<String, String> {
        let mut params = std::collections::HashMap::new();

        for part in parts {
            if let Some((key, value)) = part.split_once('=') {
                params.insert(key.to_string(), value.to_string());
            } else {
                // Handle flags without values
                params.insert(part.to_string(), "true".to_string());
            }
        }

        params
    }

    fn parse_block(params: &std::collections::HashMap<String, String>) -> Option<CXSequence> {
        let action = params.get("start").or_else(|| params.get("end"));

        if params.contains_key("start") || params.get("").map(|s| s.as_str()) == Some("start") {
            // Try to get command from either format
            let command = params
                .get("cmd")
                .cloned()
                .unwrap_or_default();
            let timestamp = params
                .get("time")
                .and_then(|t| t.parse().ok())
                .unwrap_or(0);

            return Some(CXSequence::BlockStart { command, timestamp });
        }

        if params.contains_key("end") || params.get("").map(|s| s.as_str()) == Some("end") {
            let exit_code = params
                .get("exit")
                .and_then(|e| e.parse().ok())
                .unwrap_or(0);
            let timestamp = params
                .get("time")
                .and_then(|t| t.parse().ok())
                .unwrap_or(0);

            return Some(CXSequence::BlockEnd {
                exit_code,
                timestamp,
            });
        }

        None
    }

    fn parse_prompt(params: &std::collections::HashMap<String, String>) -> Option<CXSequence> {
        if params.contains_key("start") {
            return Some(CXSequence::PromptStart);
        }
        if params.contains_key("end") {
            return Some(CXSequence::PromptEnd);
        }
        None
    }

    fn parse_cwd(params: &std::collections::HashMap<String, String>) -> Option<CXSequence> {
        params
            .get("path")
            .map(|path| CXSequence::CwdChanged { path: path.clone() })
    }

    fn parse_ai(params: &std::collections::HashMap<String, String>) -> Option<CXSequence> {
        if let Some(text) = params.get("explain").or_else(|| params.get("text")) {
            if params.contains_key("explain") {
                return Some(CXSequence::AIExplain { text: text.clone() });
            }
        }

        if let Some(query) = params.get("suggest").or_else(|| params.get("query")) {
            if params.contains_key("suggest") {
                return Some(CXSequence::AISuggest { query: query.clone() });
            }
        }

        None
    }

    fn parse_agent(params: &std::collections::HashMap<String, String>) -> Option<CXSequence> {
        let name = params.get("name")?.clone();
        let command = params.get("command").cloned().unwrap_or_default();

        Some(CXSequence::AgentRequest { name, command })
    }

    fn parse_features(params: &std::collections::HashMap<String, String>) -> Option<CXSequence> {
        Some(CXSequence::Features {
            blocks: params.get("blocks").map(|v| v == "1").unwrap_or(false),
            ai: params.get("ai").map(|v| v == "1").unwrap_or(false),
            agents: params.get("agents").map(|v| v == "1").unwrap_or(false),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_block_start() {
        let seq = BlockParser::parse("777;cx;block;start;cmd=ls -la;time=1234567890");
        match seq {
            Some(CXSequence::BlockStart { command, timestamp }) => {
                assert_eq!(command, "ls -la");
                assert_eq!(timestamp, 1234567890);
            }
            _ => panic!("Expected BlockStart"),
        }
    }

    #[test]
    fn test_parse_block_end() {
        let seq = BlockParser::parse("777;cx;block;end;exit=0;time=1234567891");
        match seq {
            Some(CXSequence::BlockEnd { exit_code, timestamp }) => {
                assert_eq!(exit_code, 0);
                assert_eq!(timestamp, 1234567891);
            }
            _ => panic!("Expected BlockEnd"),
        }
    }

    #[test]
    fn test_parse_cwd() {
        let seq = BlockParser::parse("777;cx;cwd;path=/home/user");
        match seq {
            Some(CXSequence::CwdChanged { path }) => {
                assert_eq!(path, "/home/user");
            }
            _ => panic!("Expected CwdChanged"),
        }
    }

    #[test]
    fn test_parse_features() {
        let seq = BlockParser::parse("777;cx;features;blocks=1;ai=1;agents=0");
        match seq {
            Some(CXSequence::Features { blocks, ai, agents }) => {
                assert!(blocks);
                assert!(ai);
                assert!(!agents);
            }
            _ => panic!("Expected Features"),
        }
    }

    #[test]
    fn test_non_cx_sequence() {
        let seq = BlockParser::parse("0;some title");
        assert!(seq.is_none());
    }
}
