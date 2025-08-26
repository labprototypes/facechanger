// @ts-nocheck
import React from 'react';

export const Badge: React.FC<{ children: React.ReactNode; tone?: 'default'|'accent'|'muted' } & React.HTMLAttributes<HTMLSpanElement>> = ({ tone='default', className='', ...props }) => {
  const tones = {
    default: 'bg-surface border-[color:var(--border)] text-text',
    accent: 'bg-accent text-[var(--accent-contrast)] border-transparent',
    muted: 'bg-surface2 border-[color:var(--border)] text-black/70',
  };
  return <span className={`inline-flex items-center px-2 py-1 rounded-lg text-xs border ${tones[tone]} ${className}`} {...props} />
}

export default Badge;
