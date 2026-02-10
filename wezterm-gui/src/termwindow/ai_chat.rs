// CX Terminal: AI Chat Modal
// Core AI panel UI rendered as a modal overlay using the box model system.
// Provides interactive chat with AI providers (Claude, Ollama, etc.)

use super::box_model::*;
use super::modal::Modal;
use super::render::corners::{
    BOTTOM_LEFT_ROUNDED_CORNER, BOTTOM_RIGHT_ROUNDED_CORNER, TOP_LEFT_ROUNDED_CORNER,
    TOP_RIGHT_ROUNDED_CORNER,
};
use super::TermWindow;
use crate::ai::{
    create_provider, AIAction, AIConfig, AIPanel, AIPanelState, ChatMessage, ChatRole,
};
use crate::termwindow::TermWindowNotif;
use crate::utilsprites::RenderMetrics;
use config::keyassignment::KeyAssignment;
use config::{Dimension, DimensionContext};
use std::cell::{Ref, RefCell};
use std::sync::{Arc, Mutex};
use wezterm_term::{KeyCode, KeyModifiers, MouseEvent};
use window::color::LinearRgba;
use window::WindowOps;

// CX Terminal: AI Chat Modal struct — wraps AIPanel with box-model rendering
pub struct AIChatModal {
    /// The underlying AI panel state (chat history, input, loading, etc.)
    panel: RefCell<AIPanel>,
    /// Cached computed elements for the box model renderer
    element: RefCell<Option<Vec<ComputedElement>>>,
    /// Shared slot for async AI responses to be delivered back to the modal
    pending_response: Arc<Mutex<Option<String>>>,
    /// Shared slot for async AI errors to be delivered back to the modal
    pending_error: Arc<Mutex<Option<String>>>,
    /// Scroll offset for chat history (number of messages scrolled up from bottom)
    scroll_offset: RefCell<usize>,
    /// Whether we have a pending submit to dispatch on next render (for new_with_query)
    auto_submit: RefCell<bool>,
}

impl AIChatModal {
    // CX Terminal: Create a new AI chat modal with auto-detected provider
    pub fn new(_term_window: &TermWindow) -> Self {
        let config = AIConfig::auto_detect();
        let mut panel = AIPanel::new(config);
        panel.state = AIPanelState::Chat;

        Self {
            panel: RefCell::new(panel),
            element: RefCell::new(None),
            pending_response: Arc::new(Mutex::new(None)),
            pending_error: Arc::new(Mutex::new(None)),
            scroll_offset: RefCell::new(0),
            auto_submit: RefCell::new(false),
        }
    }

    // CX Terminal: Create a new AI chat modal with a pre-filled query that submits on first render
    pub fn new_with_query(term_window: &TermWindow, query: String) -> Self {
        let modal = Self::new(term_window);
        {
            let mut panel = modal.panel.borrow_mut();
            panel.input = query;
        }
        *modal.auto_submit.borrow_mut() = true;
        modal
    }

    // CX Terminal: Submit current input and dispatch async AI request if applicable
    fn dispatch_submit(&self, term_window: &mut TermWindow) {
        let action = {
            let mut panel = self.panel.borrow_mut();
            panel.submit()
        };

        if let Some(action) = action {
            self.dispatch_async(action, term_window);
        }

        self.element.borrow_mut().take();
    }

    // CX Terminal: Dispatch an async AI provider request using promise::spawn
    fn dispatch_async(&self, action: AIAction, term_window: &mut TermWindow) {
        // Extract everything we need before the async block (self is not Send)
        let config = self.panel.borrow().config.clone();
        let system_prompt = action.system_prompt().to_string();
        let user_prompt = action.user_prompt();

        let pending_response = Arc::clone(&self.pending_response);
        let pending_error = Arc::clone(&self.pending_error);

        // Get the window handle for notifying the GUI thread when done
        let window = match term_window.window.clone() {
            Some(w) => w,
            None => {
                self.panel
                    .borrow_mut()
                    .set_error("No window handle available".to_string());
                return;
            }
        };

        promise::spawn::spawn(async move {
            let provider = create_provider(&config);
            match provider {
                Some(provider) => {
                    let api_messages = vec![ChatMessage::user(user_prompt)];
                    match provider
                        .chat_completion(api_messages, Some(system_prompt))
                        .await
                    {
                        Ok(response) => {
                            if let Ok(mut slot) = pending_response.lock() {
                                *slot = Some(response.content);
                            }
                            window.notify(TermWindowNotif::Apply(Box::new(move |tw| {
                                tw.invalidate_modal();
                            })));
                        }
                        Err(err) => {
                            let error_msg = format!("{}", err);
                            if let Ok(mut slot) = pending_error.lock() {
                                *slot = Some(error_msg);
                            }
                            window.notify(TermWindowNotif::Apply(Box::new(move |tw| {
                                tw.invalidate_modal();
                            })));
                        }
                    }
                }
                None => {
                    let error_msg = "No AI provider available. Check your configuration.".to_string();
                    if let Ok(mut slot) = pending_error.lock() {
                        *slot = Some(error_msg);
                    }
                    window.notify(TermWindowNotif::Apply(Box::new(move |tw| {
                        tw.invalidate_modal();
                    })));
                }
            }
        })
        .detach();
    }

    // CX Terminal: Drain any pending async results into the panel state
    fn drain_pending(&self) {
        // Check for a pending response
        if let Ok(mut slot) = self.pending_response.lock() {
            if let Some(response) = slot.take() {
                let mut panel = self.panel.borrow_mut();
                panel.append_response(&response);
                panel.complete_response();
            }
        }

        // Check for a pending error
        if let Ok(mut slot) = self.pending_error.lock() {
            if let Some(error) = slot.take() {
                self.panel.borrow_mut().set_error(error);
            }
        }
    }

    // CX Terminal: Build the box-model element tree for the AI chat panel
    fn compute(&self, term_window: &mut TermWindow) -> anyhow::Result<Vec<ComputedElement>> {
        // Drain any async results before rendering
        self.drain_pending();

        let panel = self.panel.borrow();

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

        // CX Terminal: Color palette — dark glass aesthetic
        let bg_color: InheritableColor =
            LinearRgba::with_components(0.05, 0.08, 0.12, 0.92).into();
        let title_color: InheritableColor =
            LinearRgba::with_components(0.0, 0.85, 1.0, 1.0).into();
        let text_color: InheritableColor =
            LinearRgba::with_components(0.9, 0.9, 0.9, 1.0).into();
        let dim_color: InheritableColor =
            LinearRgba::with_components(0.5, 0.5, 0.5, 1.0).into();
        let user_color: InheritableColor =
            LinearRgba::with_components(0.4, 0.8, 1.0, 1.0).into();
        let assistant_color: InheritableColor =
            LinearRgba::with_components(0.7, 0.9, 0.7, 1.0).into();
        let error_color: InheritableColor =
            LinearRgba::with_components(1.0, 0.3, 0.3, 1.0).into();
        let input_bg: InheritableColor =
            LinearRgba::with_components(0.08, 0.1, 0.15, 1.0).into();

        let mut children = vec![];

        // CX Terminal: Title bar with provider name
        let provider_name = panel.config.get_status().display_text();
        children.push(
            Element::new(
                &font,
                ElementContent::Text(format!(" CX AI \u{2014} {}", provider_name)),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: title_color,
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

        // CX Terminal: Separator after title
        children.push(
            Element::new(
                &font,
                ElementContent::Text(String::new()),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: dim_color.clone(),
            })
            .padding(BoxDimension {
                left: Dimension::Cells(0.0),
                right: Dimension::Cells(0.0),
                top: Dimension::Cells(0.25),
                bottom: Dimension::Cells(0.0),
            })
            .display(DisplayType::Block),
        );

        // CX Terminal: Chat messages
        let messages = panel.history.messages();
        let scroll = *self.scroll_offset.borrow();
        let visible_end = messages.len().saturating_sub(scroll);
        // Show up to 20 messages at a time
        let max_visible = 20;
        let visible_start = visible_end.saturating_sub(max_visible);
        let visible_messages = &messages[visible_start..visible_end];

        if messages.is_empty() && !panel.loading {
            // CX Terminal: Welcome message when chat is empty
            children.push(
                Element::new(
                    &font,
                    ElementContent::Text("  Ask me anything about your terminal...".into()),
                )
                .colors(ElementColors {
                    border: BorderColor::default(),
                    bg: LinearRgba::TRANSPARENT.into(),
                    text: dim_color.clone(),
                })
                .padding(BoxDimension {
                    left: Dimension::Cells(0.25),
                    right: Dimension::Cells(0.25),
                    top: Dimension::Cells(0.5),
                    bottom: Dimension::Cells(0.25),
                })
                .display(DisplayType::Block),
            );
        }

        for msg in visible_messages {
            let (prefix, color) = match msg.role {
                ChatRole::User => ("> ", user_color.clone()),
                ChatRole::Assistant => ("< ", assistant_color.clone()),
                ChatRole::System => ("# ", dim_color.clone()),
            };

            // CX Terminal: Wrap long messages into multiple lines for display
            let full_text = format!("{}{}", prefix, msg.content);
            for line in full_text.lines() {
                children.push(
                    Element::new(&font, ElementContent::Text(format!("  {}", line)))
                        .colors(ElementColors {
                            border: BorderColor::default(),
                            bg: LinearRgba::TRANSPARENT.into(),
                            text: color.clone(),
                        })
                        .padding(BoxDimension {
                            left: Dimension::Cells(0.25),
                            right: Dimension::Cells(0.25),
                            top: Dimension::Cells(0.0),
                            bottom: Dimension::Cells(0.0),
                        })
                        .display(DisplayType::Block),
                );
            }

            // CX Terminal: Small spacer between messages
            children.push(
                Element::new(&font, ElementContent::Text(String::new()))
                    .colors(ElementColors {
                        border: BorderColor::default(),
                        bg: LinearRgba::TRANSPARENT.into(),
                        text: dim_color.clone(),
                    })
                    .padding(BoxDimension {
                        left: Dimension::Cells(0.0),
                        right: Dimension::Cells(0.0),
                        top: Dimension::Cells(0.1),
                        bottom: Dimension::Cells(0.1),
                    })
                    .display(DisplayType::Block),
            );
        }

        // CX Terminal: Show streaming response if in progress
        if let Some(ref partial) = panel.streaming_response {
            let partial_text = format!("  < {}", partial);
            for line in partial_text.lines() {
                children.push(
                    Element::new(&font, ElementContent::Text(line.to_string()))
                        .colors(ElementColors {
                            border: BorderColor::default(),
                            bg: LinearRgba::TRANSPARENT.into(),
                            text: assistant_color.clone(),
                        })
                        .padding(BoxDimension {
                            left: Dimension::Cells(0.25),
                            right: Dimension::Cells(0.25),
                            top: Dimension::Cells(0.0),
                            bottom: Dimension::Cells(0.0),
                        })
                        .display(DisplayType::Block),
                );
            }
        }

        // CX Terminal: Loading indicator
        if panel.loading && panel.streaming_response.is_none() {
            children.push(
                Element::new(
                    &font,
                    ElementContent::Text("  Thinking...".into()),
                )
                .colors(ElementColors {
                    border: BorderColor::default(),
                    bg: LinearRgba::TRANSPARENT.into(),
                    text: dim_color.clone(),
                })
                .padding(BoxDimension {
                    left: Dimension::Cells(0.25),
                    right: Dimension::Cells(0.25),
                    top: Dimension::Cells(0.25),
                    bottom: Dimension::Cells(0.25),
                })
                .display(DisplayType::Block),
            );
        }

        // CX Terminal: Error display
        if let Some(ref error) = panel.error {
            children.push(
                Element::new(
                    &font,
                    ElementContent::Text(format!("  Error: {}", error)),
                )
                .colors(ElementColors {
                    border: BorderColor::default(),
                    bg: LinearRgba::TRANSPARENT.into(),
                    text: error_color,
                })
                .padding(BoxDimension {
                    left: Dimension::Cells(0.25),
                    right: Dimension::Cells(0.25),
                    top: Dimension::Cells(0.25),
                    bottom: Dimension::Cells(0.25),
                })
                .display(DisplayType::Block),
            );
        }

        // CX Terminal: Separator before input
        children.push(
            Element::new(
                &font,
                ElementContent::Text(
                    "  \u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}\u{2500}".into(),
                ),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: dim_color.clone(),
            })
            .display(DisplayType::Block),
        );

        // CX Terminal: Input field
        let input_display = format!("  > {}_ ", panel.input);
        children.push(
            Element::new(&font, ElementContent::Text(input_display))
                .colors(ElementColors {
                    border: BorderColor::default(),
                    bg: input_bg,
                    text: text_color.clone(),
                })
                .padding(BoxDimension {
                    left: Dimension::Cells(0.25),
                    right: Dimension::Cells(0.25),
                    top: Dimension::Cells(0.25),
                    bottom: Dimension::Cells(0.25),
                })
                .display(DisplayType::Block),
        );

        // CX Terminal: Help text
        children.push(
            Element::new(
                &font,
                ElementContent::Text(
                    "  Enter send \u{2022} Esc close \u{2022} Ctrl+U clear".into(),
                ),
            )
            .colors(ElementColors {
                border: BorderColor::default(),
                bg: LinearRgba::TRANSPARENT.into(),
                text: dim_color,
            })
            .padding(BoxDimension {
                left: Dimension::Cells(0.25),
                right: Dimension::Cells(0.25),
                top: Dimension::Cells(0.1),
                bottom: Dimension::Cells(0.25),
            })
            .display(DisplayType::Block),
        );

        // CX Terminal: Wrap all children in a right-aligned container (35% width)
        let total_pixel_width = term_window.dimensions.pixel_width as f32;
        let panel_width = total_pixel_width * 0.35;
        let left_margin_pixels = total_pixel_width - panel_width;
        // Convert left margin to approximate cell count
        let cell_width = term_window.render_metrics.cell_size.width as f32;
        let left_margin_cells = if cell_width > 0.0 {
            left_margin_pixels / cell_width
        } else {
            2.0
        };

        let cyan_border = LinearRgba::with_components(0.0, 0.85, 1.0, 1.0);

        let element = Element::new(&font, ElementContent::Children(children))
            .colors(ElementColors {
                border: BorderColor::new(cyan_border),
                bg: bg_color,
                text: text_color,
            })
            .margin(BoxDimension {
                left: Dimension::Cells(left_margin_cells),
                right: Dimension::Cells(0.5),
                top: Dimension::Cells(1.0),
                bottom: Dimension::Cells(1.0),
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

        // CX Terminal: Compute layout using the same pattern as TelemetryPanel
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

// CX Terminal: Modal trait implementation for AIChatModal
impl Modal for AIChatModal {
    fn perform_assignment(
        &self,
        _assignment: &KeyAssignment,
        _term_window: &mut TermWindow,
    ) -> bool {
        false
    }

    fn mouse_event(
        &self,
        _event: MouseEvent,
        _term_window: &mut TermWindow,
    ) -> anyhow::Result<()> {
        Ok(())
    }

    fn key_down(
        &self,
        key: KeyCode,
        mods: KeyModifiers,
        term_window: &mut TermWindow,
    ) -> anyhow::Result<bool> {
        match (key, mods) {
            // CX Terminal: Escape closes the AI chat modal
            (KeyCode::Escape, KeyModifiers::NONE) => {
                term_window.cancel_modal();
            }

            // CX Terminal: Enter submits the current input
            (KeyCode::Enter, KeyModifiers::NONE) => {
                self.dispatch_submit(term_window);
                term_window.invalidate_modal();
            }

            // CX Terminal: Backspace deletes the last character from input
            (KeyCode::Backspace, KeyModifiers::NONE) => {
                {
                    let mut panel = self.panel.borrow_mut();
                    panel.input.pop();
                }
                self.element.borrow_mut().take();
                term_window.invalidate_modal();
            }

            // CX Terminal: Ctrl+U clears the input line
            (KeyCode::Char('u'), KeyModifiers::CTRL) => {
                {
                    let mut panel = self.panel.borrow_mut();
                    panel.input.clear();
                    panel.clear_error();
                }
                self.element.borrow_mut().take();
                term_window.invalidate_modal();
            }

            // CX Terminal: Up arrow scrolls chat history up
            (KeyCode::UpArrow, KeyModifiers::NONE) => {
                {
                    let mut scroll = self.scroll_offset.borrow_mut();
                    let max_scroll = self.panel.borrow().history.len();
                    if *scroll < max_scroll {
                        *scroll += 1;
                    }
                }
                self.element.borrow_mut().take();
                term_window.invalidate_modal();
            }

            // CX Terminal: Down arrow scrolls chat history down
            (KeyCode::DownArrow, KeyModifiers::NONE) => {
                {
                    let mut scroll = self.scroll_offset.borrow_mut();
                    *scroll = scroll.saturating_sub(1);
                }
                self.element.borrow_mut().take();
                term_window.invalidate_modal();
            }

            // CX Terminal: Regular character input appended to the input buffer
            (KeyCode::Char(c), KeyModifiers::NONE) | (KeyCode::Char(c), KeyModifiers::SHIFT) => {
                {
                    let mut panel = self.panel.borrow_mut();
                    panel.input.push(c);
                }
                self.element.borrow_mut().take();
                term_window.invalidate_modal();
            }

            _ => return Ok(false),
        }
        Ok(true)
    }

    fn computed_element(
        &self,
        term_window: &mut TermWindow,
    ) -> anyhow::Result<Ref<'_, [ComputedElement]>> {
        // CX Terminal: Drain pending async results each time we render
        self.drain_pending();

        // CX Terminal: Handle deferred auto-submit from new_with_query
        if *self.auto_submit.borrow() {
            *self.auto_submit.borrow_mut() = false;
            self.dispatch_submit(term_window);
        }

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
