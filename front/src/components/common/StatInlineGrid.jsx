export default function StatInlineGrid({ items, columns = 6 }) {
  return (
    <div className="stat-inline-grid" style={{ '--stat-cols': columns }}>
      {items.map((item) => (
        <div className="stat-inline" key={item.label}>
          <div className="lbl">{item.label}</div>
          <div className="val">{item.value}</div>
          {item.sub ? <div className="sub">{item.sub}</div> : null}
        </div>
      ))}
    </div>
  );
}