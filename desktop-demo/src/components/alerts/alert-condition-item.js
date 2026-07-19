(() => {
function AlertConditionItem(condition, onDelete) {
  const item = document.createElement("article");
  item.className = "alert-condition-item";

  const content = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = `${condition.symbol} · ${condition.name}`;
  const rule = document.createElement("p");
  rule.textContent = condition.user_rule;
  const summary = document.createElement("small");
  summary.textContent = condition.validation_summary;
  content.append(title, rule, summary);

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "text-button danger-text";
  deleteButton.textContent = "삭제";
  deleteButton.addEventListener("click", () => onDelete(condition.id));

  item.append(content, deleteButton);
  return item;
}

window.StockAgent = { ...window.StockAgent, AlertConditionItem };
})();
