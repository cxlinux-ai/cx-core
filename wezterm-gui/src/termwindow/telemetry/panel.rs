// CX Terminal: Telemetry Panel UI
// Renders the telemetry dashboard as a modal overlay

use super::super::box_model::*;
use super::super::modal::Modal;
use super::super::render::corners::{
    BOTTOM_LEFT_ROUNDED_CORNER, BOTTOM_RIGHT_ROUNDED_CORNER, TOP_LEFT_ROUNDED_CORNER,
    TOP_RIGHT_ROUNDED_CORNER,
};
use super::super::TermWindow;
use crate::utilsprites::RenderMetrics;
use config::keyassignment::KeyAssignment;
use config::{Dimension, DimensionContext};
use std::cell::{Ref, RefCell};
use wezterm_term::{KeyCode, KeyModifiers, MouseEvent};
use window::color::LinearRgba;

use super::data::{GitStatus, TelemetryData};

/// Telemetry Panel - displays system stats and AI suggestions
pub struct TelemetryPanel {
    /// Current telemetry data
    data: RefCell<TelemetryData>,
    /// Pane ID for context
    pane_id: usize,
    /// Selected action index
    selected_action: RefCell<usize>,
    /// Available actions
    actions: Vec<TelemetryAction>,
    /// Cached computed elements
    element: RefCell<Option<Vec<ComputedElement>>>,
}

#[derive(Debug, Clone)]
pub struct TelemetryAction {
    pub label: String,
    pub key: char,
    pub command: String,
}

impl TelemetryPanel {
    pub fn new(pane_id: usize) -> Self {
        let data = TelemetryData::collect();

        let actions = vec![
            TelemetryAction {
                label: "Fix with AI".into(),
                key: 'f',
                command: "claude --fix-last-error\n".into(),
            },
            TelemetryAction {
                label: "Explain Last".into(),
                key: 'e',
                command: "claude explain\n".into(),
            },
            TelemetryAction {
                label: "Git Status".into(),
                key: 'g',
                command: "git status\n".into(),
            },
            TelemetryAction {
                label: "Run Tests".into(),
                key: 't',
                command: "cargo test\n".into(),
            },
        ];

        Self {
            data: RefCell::new(data),
            pane_id,
            selected_action: RefCell::new(0),
            actions,
            element: RefCell::new(None),
        }
    }

    fn move_selection(&self, delta: i32) {
        let mut sel = self.selected_action.borrow_mut();
        let max = self.actions.len().saturating_sub(1);
        if delta < 0 {
            *sel = sel.saturating_sub((-delta) as usize);
        } else {
            *sel = (*sel + delta as usize).min(max);
        }
        self.element.borrow_mut().take();
    }

    fn execute_selected(&self, term_window: &mut TermWindow) {
        let sel = *self.selected_action.borrow();
        if let Some(action) = self.actions.get(sel) {
            if let Some(pane) = term_window.get_active_pane_or_overlay() {
                pane.writer().write_all(action.command.as_bytes()).ok();
            }
        }
    }

    fn execute_by_key(&self, c: char, term_window: &mut TermWindow) -> bool {
        for action in &self.actions {
            if action.key == c {
                if let Some(pane) = term_window.get_active_pane_or_overlay() {
                    pane.writer().write_all(action.command.as_bytes()).ok();
                }
                return true;
            }
        }
        false
    }

    fn compute(&self, term_window: &mut TermWindow) -> anyhow::Result<Vec<ComputedElement>> {
        // Refresh data if stale
        if self.data.borrow().is_stale() {
            self.data.borrow_mut().refresh();
        }

        let data = self.data.borrow();
        let font = term_window
            .fonts
            .title_font()
            .expect("to resolve title font");
        let metrics = RenderMetrics::with_font_metrics(&font.metrics());

        let top_bar_height = if term_window.show_tab_bar && !term_window.config.tab_bar_at_bottom {
            term_window.tab_bar_pixel_height().unwrap()
        } else {
            0.
        };
        let (padding_left, padding_top) = term_window.padding_left_top();
        let border = term_window.get_os_border();
        let top_pixel_y = top_bar_height + padding_top + border.top.get() as f32;

        // Colors
        let bg_color: InheritableColor = LinearRgba::with_components(0.05, 0.08, 0.12, 0.95).into();
        let border_linear = LinearRgba::with_components(0.0, 0.8, 0.8, 1.0);
        let border_color: InheritableColor = border_linear.clone().into();
        let title_color: InheritableColor = LinearRgba::with_components(0.0, 1.0, 1.0, 1.0).into();
        let text_color: InheritableColor = LinearRgba::with_components(0.9, 0.9, 0.9, 1.0).into();
        let dim_color: InheritableColor = LinearRgba::with_components(0.5, 0.5, 0.5, 1.0).into();
        let selected_color: InheritableColor = LinearRgba::with_components(0.0, 1.0, 1.0, 1.0).into();

        let git_color: InheritableColor = match data.git_status {
            GitStatus::Clean => LinearRgba::with_components(0.0, 1.0, 0.5, 1.0).into(),
            GitStatus::Dirty => LinearRgba::with_components(1.0, 0.8, 0.0, 1.0).into(),
            GitStatus::Staged => LinearRgba::with_components(0.0, 0.8, 1.0, 1.0).into(),
            GitStatus::Mixed => LinearRgba::with_components(1.0, 0.5, 0.0, 1.0).into(),
            _ => dim_color.clone(),
        };

        let selected = *self.selected_action.borrow();

        // Build child elements
        let mut children = vec![];

        // Title
        children.push(
            Element::new(
                &font,
                ElementContent::Text(" CX Telemetry Dashboard".into()),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: border_color.clone(),
                text: LinearRgba::with_components(0.0, 0.0, 0.0, 1.0).into(),
            })
            .padding(BoxDimension {
                left: Dimension::Cells(0.5),
                right: Dimension::Cells(0.5),
                top: Dimension::Cells(0.25),
                bottom: Dimension::Cells(0.25),
            })
            .display(DisplayType::Block),
        );

        // System stats
        children.push(
            Element::new(
                &font,
                ElementContent::Text(format!("  CPU: {:.1}%", data.cpu_percent)),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: text_color.clone(),
            })
            .display(DisplayType::Block),
        );

        children.push(
            Element::new(
                &font,
                ElementContent::Text(format!(
                    "  RAM: {:.1}/{:.1} GB ({:.0}%)",
                    data.mem_used_gb, data.mem_total_gb, data.mem_percent
                )),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: text_color.clone(),
            })
            .display(DisplayType::Block),
        );

        children.push(
            Element::new(
                &font,
                ElementContent::Text(format!("  Git: {}", data.git_string())),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: git_color,
            })
            .display(DisplayType::Block),
        );

        // Separator
        children.push(
            Element::new(
                &font,
                ElementContent::Text("  ─────────────────────────────".into()),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: dim_color.clone(),
            })
            .display(DisplayType::Block),
        );

        // Actions header
        children.push(
            Element::new(
                    &font,
                    ElementContent::Text("  Actions:".into()),
                )
                .colors(ElementColors {
                    border: BorderColor::default(),
                    bg: LinearRgba::TRANSPARENT.into(),
                    text: dim_color.clone(),
                })
                .display(DisplayType::Block),
        );

        // Action items
        for (i, action) in self.actions.iter().enumerate() {
            let (bg, text) = if i == selected {
                (selected_color.clone(), LinearRgba::with_components(0.0, 0.0, 0.0, 1.0).into())
            } else {
                (LinearRgba::TRANSPARENT.into(), text_color.clone())
            };

            let prefix = if i == selected { "▶" } else { " " };
            children.push(
                Element::new(
                    &font,
                    ElementContent::Text(format!(
                        "  {} [{}] {}",
                        prefix, action.key, action.label
                    )),
                )
                .colors(ElementColors {
                    border: BorderColor::default(),
                    bg,
                    text,
                })
                .padding(BoxDimension {
                    left: Dimension::Cells(0.25),
                    right: Dimension::Cells(0.25),
                    top: Dimension::Cells(0.),
                    bottom: Dimension::Cells(0.),
                })
                .display(DisplayType::Block),
            );
        }

        // Help text
        children.push(
            Element::new(
                &font,
                ElementContent::Text("  ─────────────────────────────".into()),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: dim_color.clone(),
            })
            .display(DisplayType::Block),
        );

        children.push(
            Element::new(
                &font,
                ElementContent::Text("  ↑↓ navigate • Enter select • Esc close".into()),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: dim_color.clone(),
            })
            .display(DisplayType::Block),
        );

        // Wrap in container
        let element = Element::new(&font, ElementContent::Children(children))
            .colors(ElementColors {
                border: BorderColor::new(border_linear),
                bg: bg_color,
                text: text_color,
            })
            .margin(BoxDimension {
                left: Dimension::Cells(2.0),
                right: Dimension::Cells(2.0),
                top: Dimension::Cells(2.0),
                bottom: Dimension::Cells(2.0),
            })
            .padding(BoxDimension {
                left: Dimension::Cells(0.5),
                right: Dimension::Cells(0.5),
                top: Dimension::Cells(0.5),
                bottom: Dimension::Cells(0.5),
            })
            .border(BoxDimension::new(Dimension::Pixels(2.)))
            .border_corners(Some(Corners {
                top_left: SizedPoly {
                    width: Dimension::Cells(0.5),
                    height: Dimension::Cells(0.5),
                    poly: TOP_LEFT_ROUNDED_CORNER,
                },
                top_right: SizedPoly {
                    width: Dimension::Cells(0.5),
                    height: Dimension::Cells(0.5),
                    poly: TOP_RIGHT_ROUNDED_CORNER,
                },
                bottom_left: SizedPoly {
                    width: Dimension::Cells(0.5),
                    height: Dimension::Cells(0.5),
                    poly: BOTTOM_LEFT_ROUNDED_CORNER,
                },
                bottom_right: SizedPoly {
                    width: Dimension::Cells(0.5),
                    height: Dimension::Cells(0.5),
                    poly: BOTTOM_RIGHT_ROUNDED_CORNER,
                },
            }));

        let dimensions = term_window.dimensions;
        let size = term_window.terminal_size;

        let computed = term_window.compute_element(
            &LayoutContext {
                height: DimensionContext {
                    dpi: dimensions.dpi as f32,
                    pixel_max: dimensions.pixel_height as f32,
                    pixel_cell: metrics.cell_size.height as f32,
                },
                width: DimensionContext {
                    dpi: dimensions.dpi as f32,
                    pixel_max: dimensions.pixel_width as f32,
                    pixel_cell: metrics.cell_size.width as f32,
                },
                bounds: euclid::rect(
                    padding_left,
                    top_pixel_y,
                    size.cols as f32 * term_window.render_metrics.cell_size.width as f32,
                    size.rows as f32 * term_window.render_metrics.cell_size.height as f32,
                ),
                metrics: &metrics,
                gl_state: term_window.render_state.as_ref().unwrap(),
                zindex: 100,
            },
            &element,
        )?;

        Ok(vec![computed])
    }
}

impl Modal for TelemetryPanel {
    fn perform_assignment(
        &self,
        _assignment: &KeyAssignment,
        _term_window: &mut TermWindow,
    ) -> bool {
        false
    }

    fn mouse_event(&self, _event: MouseEvent, _term_window: &mut TermWindow) -> anyhow::Result<()> {
        Ok(())
    }

    fn key_down(
        &self,
        key: KeyCode,
        mods: KeyModifiers,
        term_window: &mut TermWindow,
    ) -> anyhow::Result<bool> {
        match (key, mods) {
            (KeyCode::Escape, KeyModifiers::NONE) => {
                term_window.cancel_modal();
            }
            (KeyCode::UpArrow, KeyModifiers::NONE) | (KeyCode::Char('k'), KeyModifiers::NONE) => {
                self.move_selection(-1);
                term_window.invalidate_modal();
            }
            (KeyCode::DownArrow, KeyModifiers::NONE) | (KeyCode::Char('j'), KeyModifiers::NONE) => {
                self.move_selection(1);
                term_window.invalidate_modal();
            }
            (KeyCode::Enter, KeyModifiers::NONE) => {
                self.execute_selected(term_window);
                term_window.cancel_modal();
            }
            (KeyCode::Char(c), KeyModifiers::NONE) => {
                if self.execute_by_key(c, term_window) {
                    term_window.cancel_modal();
                }
            }
            _ => return Ok(false),
        }
        Ok(true)
    }

    fn computed_element(
        &self,
        term_window: &mut TermWindow,
    ) -> anyhow::Result<Ref<'_, [ComputedElement]>> {
        if self.element.borrow().is_none() {
            let element = self.compute(term_window)?;
            *self.element.borrow_mut() = Some(element);
        }
        Ok(Ref::map(self.element.borrow(), |opt| {
            opt.as_ref().map(|v| v.as_slice()).unwrap_or(&[])
        }))
    }

    fn reconfigure(&self, _term_window: &mut TermWindow) {
        self.element.borrow_mut().take();
    }
}
