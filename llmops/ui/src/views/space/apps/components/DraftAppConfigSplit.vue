<template>
  <div
    class="grid h-full min-h-0 flex-1 grid-cols-1 overflow-hidden bg-white md:grid-cols-2 md:divide-x md:divide-slate-200/80"
  >
    <div
      class="min-h-0 h-full min-w-0 overflow-hidden bg-gradient-to-b from-slate-50/90 to-white md:from-slate-50/70 md:to-white"
    >
      <slot name="preset" />
    </div>
    <div
      class="min-h-0 h-full min-w-0 overflow-hidden border-t border-slate-200/80 bg-gradient-to-b from-slate-50/90 to-white md:border-t-0 md:from-white md:to-slate-50/30"
    >
      <slot name="abilities" />
    </div>
  </div>
</template>
