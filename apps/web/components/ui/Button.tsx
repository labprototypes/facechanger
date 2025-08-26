// @ts-nocheck
import React from 'react';

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary'|'secondary'|'ghost'|'destructive';
  size?: 'sm'|'md';
};

export const Button: React.FC<Props> = ({ variant='secondary', size='md', className='', ...props }) => {
  const base = 'inline-flex items-center justify-center rounded-lg border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent';
  const sizes = size==='sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3 py-2 text-sm';
  const v = {
    primary: 'bg-accent text-[var(--accent-contrast)] border-transparent hover:bg-[var(--accent-hover)] active:bg-[var(--accent-press)]',
    secondary: 'bg-surface text-text border-[color:var(--border)] hover:bg-surface2',
    ghost: 'bg-transparent text-text border-transparent hover:bg-surface2',
    destructive: 'bg-red-500 text-white border-transparent hover:bg-red-600',
  }[variant];
  return <button className={`${base} ${sizes} ${v} ${className}`} {...props} />
}

export default Button;
