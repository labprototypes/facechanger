// @ts-nocheck
import * as React from 'react';
import * as SliderPrimitive from '@radix-ui/react-slider';

export interface SliderProps extends React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root> {
  value?: number[];
  onValueChange?: (value: number[]) => void;
}

export const Slider = React.forwardRef<React.ElementRef<typeof SliderPrimitive.Root>, SliderProps>(
  ({ className='', value, onValueChange, ...props }, ref) => {
    return (
      <div className={`flex items-center gap-3 ${className}`}>
        <SliderPrimitive.Root ref={ref} className="relative flex w-40 touch-none select-none items-center" value={value} onValueChange={onValueChange} {...props}>
          <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-black/10">
            <SliderPrimitive.Range className="absolute h-full bg-accent" />
          </SliderPrimitive.Track>
          <SliderPrimitive.Thumb className="block h-4 w-4 rounded-full border border-[color:var(--border)] bg-surface shadow-sm hover:shadow transition-shadow focus:outline-none focus-visible:ring-2 focus-visible:ring-accent" />
        </SliderPrimitive.Root>
        {Array.isArray(value) && <span className="w-10 text-right tabular-nums text-xs">{value[0]}</span>}
      </div>
    );
  }
);

Slider.displayName = 'Slider';

export default Slider;
