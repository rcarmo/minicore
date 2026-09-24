/** Arrow keys move focus inside a control group; Enter/Space activate separately. */
export function toolbarNavigation(event: KeyboardEvent) {
  if (
    !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key) ||
    event.altKey ||
    event.ctrlKey ||
    event.metaKey
  )
    return;
  const group = event.currentTarget as HTMLElement;
  const buttons = [
    ...group.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"),
  ];
  const index = buttons.indexOf(event.target as HTMLButtonElement);
  if (index < 0 || !buttons.length) return;
  event.preventDefault();
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? buttons.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) %
          buttons.length;
  buttons[next].focus();
  buttons[next].scrollIntoView({ block: "nearest", inline: "nearest" });
}
