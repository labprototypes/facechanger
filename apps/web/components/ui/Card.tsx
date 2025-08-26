// @ts-nocheck
import React from 'react';

export const Card: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className='', ...props }) => {
  return <div className={`rounded-xl border border-[color:var(--border)] shadow-card bg-surface ${className}`} {...props} />
}

export default Card;
