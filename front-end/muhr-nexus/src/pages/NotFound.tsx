import { Link, useLocation } from "react-router-dom";
import { SealMark } from "@/components/muhr/primitives";

const NotFound = () => {
  const location = useLocation();
  return (
    <main className="mx-auto flex min-h-screen max-w-[1240px] flex-col justify-center gap-6 px-6">
      <SealMark className="size-10" />
      <h1 className="type-wide max-w-[16ch] text-[2.5rem] font-extrabold leading-none">There&rsquo;s nothing at this address.</h1>
      <p className="text-ink-soft">
        <span className="hash">{location.pathname}</span> isn&rsquo;t a page in Muhr.
      </p>
      <Link to="/" className="w-fit font-semibold underline decoration-rule-strong underline-offset-4 hover:decoration-ink">
        Go to the overview
      </Link>
    </main>
  );
};

export default NotFound;
