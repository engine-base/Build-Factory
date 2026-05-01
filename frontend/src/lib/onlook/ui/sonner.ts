// TODO: Build-Factory integration - replace with project toast
type ToastFn = ((msg: string, opts?: unknown) => void) & {
  success: (msg: string, opts?: unknown) => void;
  error: (msg: string, opts?: unknown) => void;
  info: (msg: string, opts?: unknown) => void;
  warning: (msg: string, opts?: unknown) => void;
  message: (msg: string, opts?: unknown) => void;
  loading: (msg: string, opts?: unknown) => void;
  dismiss: (id?: string | number) => void;
  promise: <T>(p: Promise<T> | (() => Promise<T>), opts?: unknown) => Promise<T>;
};

const stub: ToastFn = ((msg: string) => {
  if (typeof window !== 'undefined') console.info('[toast]', msg);
}) as ToastFn;
stub.success = (msg) => console.info('[toast.success]', msg);
stub.error = (msg) => console.error('[toast.error]', msg);
stub.info = (msg) => console.info('[toast.info]', msg);
stub.warning = (msg) => console.warn('[toast.warning]', msg);
stub.message = (msg) => console.info('[toast]', msg);
stub.loading = (msg) => console.info('[toast.loading]', msg);
stub.dismiss = () => {};
stub.promise = async <T,>(p: Promise<T> | (() => Promise<T>)) => {
  const result = await (typeof p === 'function' ? p() : p);
  return result;
};

export const toast = stub;
