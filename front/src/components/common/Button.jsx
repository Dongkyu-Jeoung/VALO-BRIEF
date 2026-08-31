export default function Button({ variant = 'solid', className = '', children, ...rest }) {
  const base = variant === 'ghost' ? 'btn btn-ghost' : 'btn btn-solid';
  return (
    <button className={`${base} ${className}`.trim()} {...rest}>
      {children}
    </button>
  );
}
