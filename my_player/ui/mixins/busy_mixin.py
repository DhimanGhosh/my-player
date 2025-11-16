class BusyMixin:
    """
    Mixin that manages the BusyOverlay attached to the main window.

    Expects:

      Attributes:
        self.busy   # BusyOverlay instance
      Methods:
        self.rect()         # from QMainWindow
        super().resizeEvent # from QMainWindow
    """

    def _set_busy(self, on: bool, text: str = "Working…") -> None:
        """
        Show/hide the BusyOverlay with given text.
        Logic identical to your original MyPlayerMain._set_busy
        (with small safety guards).
        """
        if not hasattr(self, "busy") or self.busy is None:
            return

        self.busy.set_text(text)
        self.busy.setGeometry(self.rect())
        if on:
            self.busy.fade_in()
        else:
            self.busy.fade_out()
