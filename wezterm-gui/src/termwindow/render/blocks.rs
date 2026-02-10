//! Block rendering - paints command block overlays in the terminal
//!
//! This module handles rendering command blocks as visual overlays,
//! including headers with status indicators, collapse toggles, and
//! action buttons.

use crate::blocks::RectF as BlockRectF;
use crate::quad::TripleLayerQuadAllocator;
use crate::termwindow::box_model::*;
use crate::utilsprites::RenderMetrics;
use ::window::RectF;
use anyhow::Context;
use config::{Dimension, DimensionContext};
use mux::tab::PositionedPane;
use window::color::LinearRgba;

/// Convert a BlockRectF to window::RectF for rendering
fn to_window_rect(r: &BlockRectF) -> RectF {
    euclid::rect(r.x, r.y, r.width, r.height)
}

impl crate::TermWindow {
    /// Paint command block overlays for a pane
    ///
    /// This renders the visual block headers, status indicators, and
    /// collapse controls on top of the terminal content.
    pub fn paint_blocks(
        &mut self,
        pos: &PositionedPane,
        layers: &mut TripleLayerQuadAllocator,
    ) -> anyhow::Result<()> {
        let pane_id = pos.pane.pane_id();

        // Get block manager for this pane
        let managers = self.block_managers.borrow();
        let manager = match managers.get(&pane_id) {
            Some(m) => m,
            None => return Ok(()), // No blocks for this pane
        };

        // Skip if no blocks
        if manager.visible_blocks().next().is_none() {
            return Ok(());
        }

        // Get viewport and dimension info
        let dims = pos.pane.get_dimensions();
        let current_viewport = self.get_viewport(pane_id);
        let viewport_top = current_viewport.unwrap_or(dims.physical_top) as usize;
        let viewport_height = dims.viewport_rows;

        // Calculate rendering coordinates
        let cell_height = self.render_metrics.cell_size.height as f32;
        let cell_width = self.render_metrics.cell_size.width as f32;

        let (padding_left, padding_top) = self.padding_left_top();
        let border = self.get_os_border();

        let tab_bar_height = if self.show_tab_bar {
            self.tab_bar_pixel_height().unwrap_or(0.)
        } else {
            0.
        };
        let top_bar_height = if self.config.tab_bar_at_bottom {
            0.0
        } else {
            tab_bar_height
        };

        let top_offset = top_bar_height + padding_top + border.top.get() as f32;
        let left_offset = padding_left + border.left.get() as f32 + (pos.left as f32 * cell_width);
        let pane_width = pos.width as f32 * cell_width;

        // Compute layouts for visible blocks
        // We need to drop the managers borrow before calling compute_layouts
        // since it needs mutable access to block_renderer
        drop(managers);

        {
            let managers = self.block_managers.borrow();
            if let Some(manager) = managers.get(&pane_id) {
                self.block_renderer.borrow_mut().compute_layouts(
                    manager,
                    viewport_top,
                    viewport_height,
                    cell_height,
                    cell_width,
                    left_offset,
                    top_offset,
                    pane_width,
                );
            }
        }

        // Now render each block layout
        let renderer = self.block_renderer.borrow();
        let config = renderer.config.clone();
        let layouts: Vec<_> = renderer.layouts().iter().cloned().collect();
        drop(renderer);
        let config = &config;

        // Get block state info for status colors
        let managers = self.block_managers.borrow();
        let manager = match managers.get(&pane_id) {
            Some(m) => m,
            None => return Ok(()),
        };

        for layout in &layouts {
            // Get the block to access its state
            let block = match manager.get(layout.block_id) {
                Some(b) => b,
                None => continue,
            };

            // Determine status color based on block state
            let status_color = match block.state {
                crate::blocks::BlockState::Running => config.running_color,
                crate::blocks::BlockState::Success => config.success_color,
                crate::blocks::BlockState::Failed => config.failure_color,
                crate::blocks::BlockState::Interrupted => config.interrupted_color,
            };

            // Render header background (layer 1 - above content, below UI)
            let header_rect = to_window_rect(&layout.header_rect);
            let header_bg = if layout.selected {
                // Slightly brighter for selected blocks
                LinearRgba::with_components(
                    config.header_bg.0 * 1.2,
                    config.header_bg.1 * 1.2,
                    config.header_bg.2 * 1.2,
                    config.header_bg.3,
                )
            } else if layout.hovered {
                // Hover highlight
                LinearRgba::with_components(
                    config.header_bg.0 + config.hover_bg.0,
                    config.header_bg.1 + config.hover_bg.1,
                    config.header_bg.2 + config.hover_bg.2,
                    config.header_bg.3,
                )
            } else {
                config.header_bg
            };

            self.filled_rectangle(layers, 1, header_rect, header_bg)
                .context("block header background")?;

            // Render status indicator (left edge)
            let status_rect = to_window_rect(&layout.status_rect);
            self.filled_rectangle(layers, 1, status_rect, status_color)
                .context("block status indicator")?;

            // Render selected block border
            if layout.selected {
                let border_width = config.border_width;
                let block_rect = &layout.block_rect;

                // Top border
                self.filled_rectangle(
                    layers,
                    1,
                    euclid::rect(block_rect.x, block_rect.y, block_rect.width, border_width),
                    config.selected_border_color,
                )
                .context("block top border")?;

                // Bottom border
                self.filled_rectangle(
                    layers,
                    1,
                    euclid::rect(
                        block_rect.x,
                        block_rect.y + block_rect.height - border_width,
                        block_rect.width,
                        border_width,
                    ),
                    config.selected_border_color,
                )
                .context("block bottom border")?;

                // Left border (after status indicator)
                self.filled_rectangle(
                    layers,
                    1,
                    euclid::rect(block_rect.x, block_rect.y, border_width, block_rect.height),
                    config.selected_border_color,
                )
                .context("block left border")?;

                // Right border
                self.filled_rectangle(
                    layers,
                    1,
                    euclid::rect(
                        block_rect.x + block_rect.width - border_width,
                        block_rect.y,
                        border_width,
                        block_rect.height,
                    ),
                    config.selected_border_color,
                )
                .context("block right border")?;
            }

            // Render collapse toggle if enabled
            if let Some(ref toggle_rect) = layout.collapse_toggle_rect {
                // Draw a simple triangle indicator
                // Right-pointing for collapsed, down-pointing for expanded
                let toggle_color = config.header_fg;

                // For now, just render a small rectangle as the toggle
                // TODO: Replace with proper triangle glyph rendering
                let indicator_size = 8.0;
                let indicator_x = toggle_rect.x + (toggle_rect.width - indicator_size) / 2.0;
                let indicator_y = toggle_rect.y + (toggle_rect.height - indicator_size) / 2.0;

                self.filled_rectangle(
                    layers,
                    1,
                    euclid::rect(indicator_x, indicator_y, indicator_size, indicator_size),
                    toggle_color.mul_alpha(0.7),
                )
                .context("collapse toggle")?;
            }

            // Render action buttons on hover
            if layout.hovered {
                for (button_rect, _element) in &layout.action_buttons {
                    // Render button background
                    self.filled_rectangle(
                        layers,
                        2,
                        to_window_rect(button_rect),
                        config.hover_bg.mul_alpha(0.5),
                    )
                    .context("action button")?;
                }
            }
        }

        // Second pass: Render text in block headers
        // We use the box model Element system for text rendering
        drop(managers);

        let font = self.fonts.title_font()?;
        let metrics = RenderMetrics::with_font_metrics(&font.metrics());

        let managers = self.block_managers.borrow();
        let manager = match managers.get(&pane_id) {
            Some(m) => m,
            None => return Ok(()),
        };

        for layout in &layouts {
            let block = match manager.get(layout.block_id) {
                Some(b) => b,
                None => continue,
            };

            let header_rect = &layout.header_rect;

            // Build text for the header
            let collapse_indicator = if block.collapsed { "\u{25b6} " } else { "\u{25bc} " };
            let command_text = if block.command.is_empty() { "(unknown)" } else { &block.command };
            let duration_text = block.duration_display();

            let display_text = format!("{}{}", collapse_indicator, command_text);

            // Determine status color for the collapse indicator
            let status_color = match block.state {
                crate::blocks::BlockState::Running => config.running_color,
                crate::blocks::BlockState::Success => config.success_color,
                crate::blocks::BlockState::Failed => config.failure_color,
                crate::blocks::BlockState::Interrupted => config.interrupted_color,
            };

            // Create text element for command
            let cmd_element = Element::new(
                &font,
                ElementContent::Text(display_text),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: config.header_fg.into(),
            })
            .display(DisplayType::Inline);

            // Create duration element (right-aligned)
            let dur_element = Element::new(
                &font,
                ElementContent::Text(format!(" {}", duration_text)),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: status_color.mul_alpha(0.8).into(),
            })
            .display(DisplayType::Inline);

            // Wrap in a container positioned at the header
            let container = Element::new(
                &font,
                ElementContent::Children(vec![cmd_element, dur_element]),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: config.header_fg.into(),
            })
            .padding(BoxDimension {
                left: Dimension::Pixels(config.status_indicator_width + 8.0),
                right: Dimension::Pixels(4.0),
                top: Dimension::Pixels(2.0),
                bottom: Dimension::Pixels(2.0),
            })
            .display(DisplayType::Block);

            // Compute and render the element at the header position
            if let Some(render_state) = self.render_state.as_ref() {
                let computed = self.compute_element(
                    &LayoutContext {
                        height: DimensionContext {
                            dpi: self.dimensions.dpi as f32,
                            pixel_max: header_rect.height,
                            pixel_cell: metrics.cell_size.height as f32,
                        },
                        width: DimensionContext {
                            dpi: self.dimensions.dpi as f32,
                            pixel_max: header_rect.width,
                            pixel_cell: metrics.cell_size.width as f32,
                        },
                        bounds: euclid::rect(
                            header_rect.x,
                            header_rect.y,
                            header_rect.width,
                            header_rect.height,
                        ),
                        metrics: &metrics,
                        gl_state: render_state,
                        zindex: 10,
                    },
                    &container,
                )?;

                self.render_element(&computed, render_state, None)?;
            }
        }

        Ok(())
    }
}
