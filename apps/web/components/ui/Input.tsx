// @ts-nocheck
import React from 'react';

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input(props, ref){
  const { className='', ...rest } = props;
  return <input ref={ref} className={`w-full rounded-lg border border-[color:var(--border)] bg-surface px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-accent ${className}`} {...rest} />
});

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(props, ref){
  const { className='', ...rest } = props;
  return <textarea ref={ref} className={`w-full rounded-lg border border-[color:var(--border)] bg-surface px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-accent ${className}`} {...rest} />
});

export const Select: React.FC<React.SelectHTMLAttributes<HTMLSelectElement>> = ({ className='', ...rest }) => {
  return <select className={`w-full rounded-lg border border-[color:var(--border)] bg-surface px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-accent ${className}`} {...rest} />
}

export default Input;
