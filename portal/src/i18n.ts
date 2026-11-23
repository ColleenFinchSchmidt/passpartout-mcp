export type Locale = "en" | "it";

type TranslationStrings = {
  nav: { results: string; offers: string; calendar: string; setup: string };
  demo: string;
  login: {
    title: string;
    subtitle: string;
    email: string;
    send: string;
    demoLogin: string;
    demoHint: string;
  };
  offers: {
    title: string;
    empty: string;
    approve: string;
    edit: string;
    skip: string;
    whyNow: string;
    nights: string;
    rooms: string;
    publicPrice: string;
    privatePrice: string;
    perNight: string;
    target: string;
  };
  calendar: { title: string; comingSoon: string };
  results: { title: string; comingSoon: string };
  setup: { title: string; comingSoon: string; amenities: string; segments: string; experiences: string; guardrails: string };
};

const translations: Record<Locale, TranslationStrings> = {
  en: {
    nav: {
      results: "Results",
      offers: "Offers",
      calendar: "Calendar & rules",
      setup: "Set-up",
    },
    demo: "Demo data",
    login: {
      title: "Sign in",
      subtitle: "Enter your email to access the hotel portal",
      email: "Email address",
      send: "Send magic link",
      demoLogin: "Demo login",
      demoHint: "Skip straight in with demo data",
    },
    offers: {
      title: "Today's offers",
      empty: "No offers to show right now. The engine checks weather, events and availability every day.",
      approve: "Approve",
      edit: "Edit",
      skip: "Skip",
      whyNow: "Why now",
      nights: "nights",
      rooms: "rooms available",
      publicPrice: "Public",
      privatePrice: "Private",
      perNight: "/night",
      target: "Target",
    },
    calendar: {
      title: "Calendar & rules",
      comingSoon: "Calendar and rules editor coming in Phase 4.",
    },
    results: {
      title: "Results",
      comingSoon: "Results dashboard coming in Phase 5.",
    },
    setup: {
      title: "Set-up",
      comingSoon: "",
      amenities: "Amenities",
      segments: "Target segments",
      experiences: "Experiences",
      guardrails: "Pricing guardrails",
    },
  },
  it: {
    nav: {
      results: "Risultati",
      offers: "Offerte",
      calendar: "Calendario e regole",
      setup: "Impostazioni",
    },
    demo: "Dati demo",
    login: {
      title: "Accedi",
      subtitle: "Inserisci la tua email per accedere al portale",
      email: "Indirizzo email",
      send: "Invia link magico",
      demoLogin: "Accesso demo",
      demoHint: "Entra subito con i dati demo",
    },
    offers: {
      title: "Offerte di oggi",
      empty: "Nessuna offerta al momento. Il motore controlla meteo, eventi e disponibilità ogni giorno.",
      approve: "Approva",
      edit: "Modifica",
      skip: "Salta",
      whyNow: "Perché ora",
      nights: "notti",
      rooms: "camere disponibili",
      publicPrice: "Pubblico",
      privatePrice: "Privato",
      perNight: "/notte",
      target: "Destinatari",
    },
    calendar: {
      title: "Calendario e regole",
      comingSoon: "Editor calendario e regole in arrivo nella Fase 4.",
    },
    results: {
      title: "Risultati",
      comingSoon: "Dashboard risultati in arrivo nella Fase 5.",
    },
    setup: {
      title: "Impostazioni",
      comingSoon: "",
      amenities: "Servizi",
      segments: "Segmenti target",
      experiences: "Esperienze",
      guardrails: "Regole di prezzo",
    },
  },
};

export type Translations = TranslationStrings;

export function t(locale: Locale): Translations {
  return translations[locale];
}
