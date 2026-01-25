//! Block Renderer - renders command blocks as overlays in the terminal
//!
//! This module handles the visual rendering of command blocks including:
//! - Block headers with command, status, and duration
//! - Collapse/expand controls
//! - Block borders and separators
//! - Block selection highlighting
//! - Click hit-testing for block controls

use super::block::{Block, BlockId, BlockState};
use super::manager::BlockManager;
use std::ops::Range;
use window::color::LinearRgba;

/// Block rendering configuration
#[derive(Debug, Clone)]
pub struct BlockRenderConfig {
    /// Color for successful command indicator
    pub success_color: LinearRgba,
    /// Color for failed command indicator
    pub failure_color: LinearRgba,
    /// Color for running command indicator
    pub running_color: LinearRgba,
    /// Color for interrupted command indicator
    pub interrupted_color: LinearRgba,
    /// Color for block header background
    pub header_bg: LinearRgba,
    /// Color for block header text
    pub header_fg: LinearRgba,
    /// Color for block border
    pub border_color: LinearRgba,
    /// Color for selected block border
    pub selected_border_color: LinearRgba,
    /// Color for hovered block
    pub hover_bg: LinearRgba,
    /// Height of block header in pixels
    pub header_height: f32,
    /// Width of status indicator
    pub status_indicator_width: f32,
    /// Border width
    pub border_width: f32,
    /// Whether to show block duration
    pub show_duration: bool,
    /// Whether to show collapse controls
    pub show_collapse_controls: bool,
    /// Padding inside block header
    pub header_padding: f32,
}

impl Default for BlockRenderConfig {
    fn default() -> Self {
        Self {
            // Green for success
            success_color: LinearRgba::with_components(0.2, 0.8, 0.2, 1.0),
            // Red for failure
            failure_color: LinearRgba::with_components(0.9, 0.2, 0.2, 1.0),
            // Yellow/orange for running
            running_color: LinearRgba::with_components(0.9, 0.7, 0.1, 1.0),
            // Gray for interrupted
            interrupted_color: LinearRgba::with_components(0.5, 0.5, 0.5, 1.0),
            // Semi-transparent dark background
            header_bg: LinearRgba::with_components(0.15, 0.15, 0.18, 0.95),
            // Light gray text
            header_fg: LinearRgba::with_components(0.85, 0.85, 0.85, 1.0),
            // Subtle border
            border_color: LinearRgba::with_components(0.3, 0.3, 0.35, 0.8),
            // Highlighted border for selection
            selected_border_color: LinearRgba::with_components(0.4, 0.6, 1.0, 1.0),
            // Subtle hover highlight
            hover_bg: LinearRgba::with_components(0.2, 0.2, 0.25, 0.3),
            header_height: 24.0,
            status_indicator_width: 4.0,
            border_width: 1.0,
            show_duration: true,
            show_collapse_controls: true,
            header_padding: 8.0,
        }
    }
}

/// A UI element within a block that can be clicked
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BlockUIElement {
    /// The block header area
    Header(BlockId),
    /// The collapse/expand toggle
    CollapseToggle(BlockId),
    /// The copy command button
    CopyCommand(BlockId),
    /// The rerun button
    RerunButton(BlockId),
    /// The AI explain button
    ExplainButton(BlockId),
    /// The status indicator
    StatusIndicator(BlockId),
    /// The block content area
    Content(BlockId),
    /// The block border (for resizing or selection)
    Border(BlockId),
}

/// A clickable region within a rendered block
#[derive(Debug, Clone)]
pub struct BlockHitRegion {
    /// X coordinate (pixels from left)
    pub x: f32,
    /// Y coordinate (pixels from top)
    pub y: f32,
    /// Width in pixels
    pub width: f32,
    /// Height in pixels
    pub height: f32,
    /// What this region represents
    pub element: BlockUIElement,
}

impl BlockHitRegion {
    /// Create a new hit region
    pub fn new(x: f32, y: f32, width: f32, height: f32, element: BlockUIElement) -> Self {
        Self {
            x,
            y,
            width,
            height,
            element,
        }
    }

    /// Check if a point is within this region
    pub fn contains(&self, x: f32, y: f32) -> bool {
        x >= self.x && x < self.x + self.width && y >= self.y && y < self.y + self.height
    }
}

/// Computed layout for a single block
#[derive(Debug, Clone)]
pub struct BlockLayout {
    /// The block ID
    pub block_id: BlockId,
    /// Screen coordinates for the block header
    pub header_rect: RectF,
    /// Screen coordinates for the entire block (including content)
    pub block_rect: RectF,
    /// Screen coordinates for the status indicator
    pub status_rect: RectF,
    /// Screen coordinates for the collapse toggle
    pub collapse_toggle_rect: Option<RectF>,
    /// Screen coordinates for the command text
    pub command_text_rect: RectF,
    /// Screen coordinates for the duration text
    pub duration_rect: Option<RectF>,
    /// Screen coordinates for action buttons
    pub action_buttons: Vec<(RectF, BlockUIElement)>,
    /// Lines this block covers (for content)
    pub line_range: Range<usize>,
    /// Whether the block is collapsed
    pub collapsed: bool,
    /// Whether the block is currently hovered
    pub hovered: bool,
    /// Whether the block is selected
    pub selected: bool,
}

/// Simple rectangle struct for layout
#[derive(Debug, Clone, Copy, Default)]
pub struct RectF {
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
}

impl RectF {
    pub fn new(x: f32, y: f32, width: f32, height: f32) -> Self {
        Self {
            x,
            y,
            width,
            height,
        }
    }

    pub fn contains(&self, px: f32, py: f32) -> bool {
        px >= self.x && px < self.x + self.width && py >= self.y && py < self.y + self.height
    }

    pub fn min_x(&self) -> f32 {
        self.x
    }

    pub fn min_y(&self) -> f32 {
        self.y
    }

    pub fn max_x(&self) -> f32 {
        self.x + self.width
    }

    pub fn max_y(&self) -> f32 {
        self.y + self.height
    }

    pub fn to_euclid(&self) -> euclid::Rect<f32, f32> {
        euclid::rect(self.x, self.y, self.width, self.height)
    }
}

/// Renderer for command blocks
pub struct BlockRenderer {
    /// Rendering configuration
    pub config: BlockRenderConfig,
    /// Computed layouts for visible blocks
    layouts: Vec<BlockLayout>,
    /// Hit regions for click detection
    hit_regions: Vec<BlockHitRegion>,
    /// Currently hovered block
    hovered_block: Option<BlockId>,
    /// Currently hovered element
    hovered_element: Option<BlockUIElement>,
}

impl BlockRenderer {
    /// Create a new block renderer with default config
    pub fn new() -> Self {
        Self {
            config: BlockRenderConfig::default(),
            layouts: Vec::new(),
            hit_regions: Vec::new(),
            hovered_block: None,
            hovered_element: None,
        }
    }

    /// Create a new block renderer with custom config
    pub fn with_config(config: BlockRenderConfig) -> Self {
        Self {
            config,
            layouts: Vec::new(),
            hit_regions: Vec::new(),
            hovered_block: None,
            hovered_element: None,
        }
    }

    /// Get the color for a block's status indicator
    pub fn status_color(&self, state: BlockState) -> LinearRgba {
        match state {
            BlockState::Running => self.config.running_color,
            BlockState::Success => self.config.success_color,
            BlockState::Failed => self.config.failure_color,
            BlockState::Interrupted => self.config.interrupted_color,
        }
    }

    /// Compute layouts for all visible blocks
    ///
    /// # Arguments
    /// * `manager` - The block manager containing block state
    /// * `viewport_top` - The top line of the visible viewport
    /// * `viewport_height` - Number of visible lines
    /// * `cell_height` - Height of a single cell in pixels
    /// * `cell_width` - Width of a single cell in pixels
    /// * `left_offset` - Left padding in pixels
    /// * `top_offset` - Top padding in pixels (including tab bar, etc.)
    /// * `pane_width` - Width of the pane in pixels
    pub fn compute_layouts(
        &mut self,
        manager: &BlockManager,
        viewport_top: usize,
        viewport_height: usize,
        cell_height: f32,
        cell_width: f32,
        left_offset: f32,
        top_offset: f32,
        pane_width: f32,
    ) {
        self.layouts.clear();
        self.hit_regions.clear();

        let viewport_bottom = viewport_top + viewport_height;

        for block in manager.visible_blocks() {
            // Skip blocks outside the viewport
            if block.end_line <= viewport_top || block.start_line >= viewport_bottom {
                continue;
            }

            let layout = self.compute_block_layout(
                block,
                viewport_top,
                cell_height,
                cell_width,
                left_offset,
                top_offset,
                pane_width,
                manager.selected().map(|b| b.id) == Some(block.id),
            );

            // Generate hit regions for this block
            self.generate_hit_regions(&layout);

            self.layouts.push(layout);
        }
    }

    /// Compute layout for a single block
    fn compute_block_layout(
        &self,
        block: &Block,
        viewport_top: usize,
        cell_height: f32,
        _cell_width: f32,
        left_offset: f32,
        top_offset: f32,
        pane_width: f32,
        selected: bool,
    ) -> BlockLayout {
        let config = &self.config;

        // Calculate the visual start line (relative to viewport)
        let visual_start =
            (block.start_line as isize - viewport_top as isize).max(0) as f32 * cell_height;

        // Header position
        let header_y = top_offset + visual_start;
        let header_rect = RectF::new(left_offset, header_y, pane_width, config.header_height);

        // Status indicator (left side)
        let status_rect = RectF::new(
            left_offset,
            header_y,
            config.status_indicator_width,
            config.header_height,
        );

        // Collapse toggle (after status indicator)
        let collapse_toggle_rect = if config.show_collapse_controls {
            Some(RectF::new(
                left_offset + config.status_indicator_width + config.header_padding,
                header_y + (config.header_height - 16.0) / 2.0, // Centered vertically
                16.0,
                16.0,
            ))
        } else {
            None
        };

        // Command text area
        let command_x = if config.show_collapse_controls {
            left_offset + config.status_indicator_width + config.header_padding + 16.0 + 8.0
        } else {
            left_offset + config.status_indicator_width + config.header_padding
        };

        // Duration text area (right side)
        let duration_rect = if config.show_duration && block.duration.is_some() {
            let duration_width = 60.0; // Enough for "59m 59s"
            Some(RectF::new(
                left_offset + pane_width - config.header_padding - duration_width,
                header_y + (config.header_height - 14.0) / 2.0,
                duration_width,
                14.0,
            ))
        } else {
            None
        };

        let command_width = duration_rect
            .as_ref()
            .map(|d| d.x - command_x - 8.0)
            .unwrap_or(pane_width - (command_x - left_offset) - config.header_padding);

        let command_text_rect = RectF::new(
            command_x,
            header_y + (config.header_height - 14.0) / 2.0,
            command_width,
            14.0,
        );

        // Calculate block content area
        let content_start_line = block.start_line + 1; // Skip the header line
        let content_lines = if block.collapsed {
            0
        } else {
            block.end_line.saturating_sub(content_start_line)
        };

        let content_height = content_lines as f32 * cell_height;
        let block_height = config.header_height + content_height;

        let block_rect = RectF::new(left_offset, header_y, pane_width, block_height);

        // Action buttons (shown on hover) - positioned on the right side of header
        let mut action_buttons = Vec::new();
        let button_size = 20.0;
        let button_spacing = 4.0;
        let buttons_y = header_y + (config.header_height - button_size) / 2.0;

        // Copy command button
        let copy_x = left_offset + pane_width - config.header_padding - button_size;
        action_buttons.push((
            RectF::new(copy_x, buttons_y, button_size, button_size),
            BlockUIElement::CopyCommand(block.id),
        ));

        // Rerun button
        let rerun_x = copy_x - button_size - button_spacing;
        action_buttons.push((
            RectF::new(rerun_x, buttons_y, button_size, button_size),
            BlockUIElement::RerunButton(block.id),
        ));

        // Explain button (AI)
        let explain_x = rerun_x - button_size - button_spacing;
        action_buttons.push((
            RectF::new(explain_x, buttons_y, button_size, button_size),
            BlockUIElement::ExplainButton(block.id),
        ));

        BlockLayout {
            block_id: block.id,
            header_rect,
            block_rect,
            status_rect,
            collapse_toggle_rect,
            command_text_rect,
            duration_rect,
            action_buttons,
            line_range: block.start_line..block.end_line,
            collapsed: block.collapsed,
            hovered: self.hovered_block == Some(block.id),
            selected,
        }
    }

    /// Generate hit regions for a block layout
    fn generate_hit_regions(&mut self, layout: &BlockLayout) {
        // Header hit region
        self.hit_regions.push(BlockHitRegion::new(
            layout.header_rect.x,
            layout.header_rect.y,
            layout.header_rect.width,
            layout.header_rect.height,
            BlockUIElement::Header(layout.block_id),
        ));

        // Status indicator
        self.hit_regions.push(BlockHitRegion::new(
            layout.status_rect.x,
            layout.status_rect.y,
            layout.status_rect.width,
            layout.status_rect.height,
            BlockUIElement::StatusIndicator(layout.block_id),
        ));

        // Collapse toggle
        if let Some(ref toggle_rect) = layout.collapse_toggle_rect {
            self.hit_regions.push(BlockHitRegion::new(
                toggle_rect.x,
                toggle_rect.y,
                toggle_rect.width,
                toggle_rect.height,
                BlockUIElement::CollapseToggle(layout.block_id),
            ));
        }

        // Action buttons
        for (rect, element) in &layout.action_buttons {
            self.hit_regions.push(BlockHitRegion::new(
                rect.x,
                rect.y,
                rect.width,
                rect.height,
                element.clone(),
            ));
        }

        // Content area (if not collapsed)
        if !layout.collapsed && layout.block_rect.height > layout.header_rect.height {
            let content_y = layout.header_rect.max_y();
            let content_height = layout.block_rect.height - layout.header_rect.height;
            self.hit_regions.push(BlockHitRegion::new(
                layout.block_rect.x,
                content_y,
                layout.block_rect.width,
                content_height,
                BlockUIElement::Content(layout.block_id),
            ));
        }
    }

    /// Hit test a point and return the UI element at that position
    pub fn hit_test(&self, x: f32, y: f32) -> Option<&BlockUIElement> {
        // Check in reverse order so newer (front) elements are tested first
        for region in self.hit_regions.iter().rev() {
            if region.contains(x, y) {
                return Some(&region.element);
            }
        }
        None
    }

    /// Update hover state based on mouse position
    pub fn update_hover(&mut self, x: f32, y: f32) -> bool {
        let old_block = self.hovered_block;
        let old_element = self.hovered_element.clone();

        // Clone the element before the borrow ends
        let new_element = self.hit_test(x, y).cloned();

        match new_element {
            Some(element) => {
                let block_id = match &element {
                    BlockUIElement::Header(id)
                    | BlockUIElement::CollapseToggle(id)
                    | BlockUIElement::CopyCommand(id)
                    | BlockUIElement::RerunButton(id)
                    | BlockUIElement::ExplainButton(id)
                    | BlockUIElement::StatusIndicator(id)
                    | BlockUIElement::Content(id)
                    | BlockUIElement::Border(id) => *id,
                };
                self.hovered_element = Some(element);
                self.hovered_block = Some(block_id);
            }
            None => {
                self.hovered_block = None;
                self.hovered_element = None;
            }
        }

        old_block != self.hovered_block || old_element != self.hovered_element
    }

    /// Clear hover state
    pub fn clear_hover(&mut self) {
        self.hovered_block = None;
        self.hovered_element = None;
    }

    /// Get the currently hovered block ID
    pub fn hovered_block(&self) -> Option<BlockId> {
        self.hovered_block
    }

    /// Get the currently hovered element
    pub fn hovered_element(&self) -> Option<&BlockUIElement> {
        self.hovered_element.as_ref()
    }

    /// Get all computed layouts
    pub fn layouts(&self) -> &[BlockLayout] {
        &self.layouts
    }

    /// Find the layout for a specific block
    pub fn layout_for_block(&self, block_id: BlockId) -> Option<&BlockLayout> {
        self.layouts.iter().find(|l| l.block_id == block_id)
    }

    /// Get the block at a given line number
    pub fn block_at_line(&self, line: usize) -> Option<BlockId> {
        for layout in &self.layouts {
            if layout.line_range.contains(&line) {
                return Some(layout.block_id);
            }
        }
        None
    }
}

impl Default for BlockRenderer {
    fn default() -> Self {
        Self::new()
    }
}

/// Information needed to render a block header
#[derive(Debug, Clone)]
pub struct BlockHeaderRenderInfo {
    /// The block being rendered
    pub block_id: BlockId,
    /// Command text to display
    pub command: String,
    /// Block state for status color
    pub state: BlockState,
    /// Duration text (if completed)
    pub duration_text: Option<String>,
    /// Working directory
    pub working_dir: String,
    /// Whether the block is collapsed
    pub collapsed: bool,
    /// Whether the block is hovered
    pub hovered: bool,
    /// Whether the block is selected
    pub selected: bool,
    /// Layout information
    pub layout: BlockLayout,
}

impl BlockHeaderRenderInfo {
    /// Create render info from a block and its layout
    pub fn from_block_and_layout(block: &Block, layout: BlockLayout) -> Self {
        Self {
            block_id: block.id,
            command: block.command.clone(),
            state: block.state,
            duration_text: if block.state != BlockState::Running {
                Some(block.duration_display())
            } else {
                None
            },
            working_dir: block.working_dir.clone(),
            collapsed: block.collapsed,
            hovered: layout.hovered,
            selected: layout.selected,
            layout,
        }
    }
}

/// Generate render info for all visible blocks
pub fn collect_render_info(manager: &BlockManager, renderer: &BlockRenderer) -> Vec<BlockHeaderRenderInfo> {
    let mut result = Vec::new();

    for layout in renderer.layouts() {
        if let Some(block) = manager.get(layout.block_id) {
            result.push(BlockHeaderRenderInfo::from_block_and_layout(block, layout.clone()));
        }
    }

    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rect_contains() {
        let rect = RectF::new(10.0, 20.0, 100.0, 50.0);
        assert!(rect.contains(50.0, 40.0));
        assert!(rect.contains(10.0, 20.0));
        assert!(!rect.contains(5.0, 40.0));
        assert!(!rect.contains(50.0, 75.0));
    }

    #[test]
    fn test_hit_region() {
        let region = BlockHitRegion::new(
            0.0,
            0.0,
            100.0,
            24.0,
            BlockUIElement::Header(BlockId(0)),
        );
        assert!(region.contains(50.0, 12.0));
        assert!(!region.contains(150.0, 12.0));
    }

    #[test]
    fn test_status_color() {
        let renderer = BlockRenderer::new();

        // Running should be yellow/orange
        let running = renderer.status_color(BlockState::Running);
        assert!(running.0 > 0.5); // Red component
        assert!(running.1 > 0.5); // Green component

        // Success should be green
        let success = renderer.status_color(BlockState::Success);
        assert!(success.1 > success.0); // More green than red

        // Failed should be red
        let failed = renderer.status_color(BlockState::Failed);
        assert!(failed.0 > failed.1); // More red than green
    }
}
