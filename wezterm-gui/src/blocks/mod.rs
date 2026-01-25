//! Command Blocks System for CX Terminal
//!
//! This module implements Warp-style command blocks that group
//! terminal output into collapsible, interactive units.

mod block;
mod manager;
mod parser;
mod renderer;

pub use block::{BlockId, BlockAction};
// Block and BlockState available but currently only used internally
#[allow(unused_imports)]
pub use block::{Block, BlockState};
pub use manager::{BlockManager, BlockActionResult, BlockStats, BlockLearningData};
pub use parser::CXSequence;
// BlockParser available but currently only used internally
#[allow(unused_imports)]
pub use parser::BlockParser;
pub use renderer::{BlockRenderer, BlockUIElement};
// Additional renderer types available for future use
#[allow(unused_imports)]
pub use renderer::{
    BlockRenderConfig, BlockLayout, BlockHitRegion,
    BlockHeaderRenderInfo, RectF, collect_render_info,
};

// chrono types available for timestamp handling
#[allow(unused_imports)]
use chrono::{DateTime, Utc};
#[allow(unused_imports)]
use std::time::Duration;

/// OSC sequence prefix for CX Terminal extensions
#[allow(dead_code)]
pub const CX_OSC_PREFIX: &str = "777;cx;";

/// Block boundary markers
#[allow(dead_code)]
pub mod markers {
    pub const BLOCK_START: &str = "block;start";
    pub const BLOCK_END: &str = "block;end";
    pub const PROMPT_START: &str = "prompt;start";
    pub const PROMPT_END: &str = "prompt;end";
}
