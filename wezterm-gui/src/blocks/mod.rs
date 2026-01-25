//! Command Blocks System for CX Terminal
//!
//! This module implements Warp-style command blocks that group
//! terminal output into collapsible, interactive units.

mod block;
mod manager;
mod parser;
mod renderer;

pub use block::{Block, BlockId, BlockState, BlockAction};
pub use manager::{BlockManager, BlockActionResult, BlockStats};
pub use parser::{BlockParser, CXSequence};
pub use renderer::{
    BlockRenderer, BlockRenderConfig, BlockLayout, BlockUIElement,
    BlockHitRegion, BlockHeaderRenderInfo, RectF, collect_render_info,
};

use chrono::{DateTime, Utc};
use std::time::Duration;

/// OSC sequence prefix for CX Terminal extensions
pub const CX_OSC_PREFIX: &str = "777;cx;";

/// Block boundary markers
pub mod markers {
    pub const BLOCK_START: &str = "block;start";
    pub const BLOCK_END: &str = "block;end";
    pub const PROMPT_START: &str = "prompt;start";
    pub const PROMPT_END: &str = "prompt;end";
}
