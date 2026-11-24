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
    noOffer: string;
    createAnyway: string;
    seeTheData: string;
    whyTheseDates: string;
    roomsFree: string;
  };
  calendar: {
    title: string;
    freeRooms: string;
    blocked: string;
    events: string;
    offers: string;
    schoolHoliday: string;
    ponte: string;
    weekend: string;
    rules: string;
    publicRate: string;
    lowestPrice: string;
    maxDiscount: string;
    maxRooms: string;
    blackoutDates: string;
    bookingWindow: string;
    offerLifetime: string;
    contactCooldown: string;
    autoSend: string;
    autoWaves: string;
    save: string;
    saved: string;
    days: string;
    hours: string;
    perNight: string;
    high: string;
    medium: string;
    low: string;
    veryLow: string;
  };
  results: {
    title: string;
    offersSent: string;
    bookings: string;
    revenue: string;
    commission: string;
    uplift: string;
    holdback: string;
    perOffer: string;
    bySegment: string;
    byCity: string;
    byPackage: string;
    backtest: string;
    learnings: string;
    noData: string;
    demoLabel: string;
    months: string;
    flagged: string;
    sent: string;
    opened: string;
    clicked: string;
    booked: string;
    roomsLeft: string;
    skipped: string;
  };
  setup: { title: string; comingSoon: string; amenities: string; segments: string; experiences: string; guardrails: string; importData: string; importHint: string; dpaNotice: string };
  import: {
    title: string;
    subtitle: string;
    dropHere: string;
    browse: string;
    formats: string;
    maxSize: string;
    uploading: string;
    parsing: string;
    preview: string;
    confirm: string;
    cancel: string;
    back: string;
    noData: string;
    found: string;
    rows: string;
    problems: string;
    rooms: string;
    occupancy: string;
    monthly_occupancy: string;
    rates: string;
    guests: string;
    amenities: string;
    extras: string;
    history: string;
    undo: string;
    deleteGuests: string;
    deleteGuestsConfirm: string;
    consentMissing: string;
    duplicateEmails: string;
    unreadableDates: string;
  };
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
      noOffer: "No offer",
      createAnyway: "Create an offer anyway",
      seeTheData: "See the data",
      whyTheseDates: "Why these dates",
      roomsFree: "rooms free",
    },
    calendar: {
      title: "Calendar & rules",
      freeRooms: "free",
      blocked: "Blocked",
      events: "Events",
      offers: "Offers sent",
      schoolHoliday: "School holiday",
      ponte: "Long weekend",
      weekend: "Weekend",
      rules: "Rules",
      publicRate: "Public rate",
      lowestPrice: "Floor price",
      maxDiscount: "Max discount",
      maxRooms: "Max rooms/offer",
      blackoutDates: "Blocked dates",
      bookingWindow: "Booking window",
      offerLifetime: "Offer lifetime",
      contactCooldown: "Contact cooldown",
      autoSend: "Auto-send offers",
      autoWaves: "Auto-send waves",
      save: "Save rules",
      saved: "Saved",
      days: "days",
      hours: "hours",
      perNight: "/night",
      high: "High",
      medium: "Medium",
      low: "Low",
      veryLow: "Very low",
    },
    results: {
      title: "Results",
      offersSent: "Offers sent",
      bookings: "Bookings",
      revenue: "Revenue",
      commission: "Commission (15%)",
      uplift: "Uplift vs holdback",
      holdback: "10% holdback group",
      perOffer: "Per offer & wave",
      bySegment: "By segment",
      byCity: "By city",
      byPackage: "By package / extras",
      backtest: "12-month back-test",
      learnings: "What the engine has learned",
      noData: "Not enough data yet. Send a few offers and results will appear here.",
      demoLabel: "Simulated demo data",
      months: "months",
      flagged: "flagged",
      sent: "Sent",
      opened: "Opened",
      clicked: "Clicked",
      booked: "Booked",
      roomsLeft: "Rooms left",
      skipped: "Skipped",
    },
    setup: {
      title: "Set-up",
      comingSoon: "",
      amenities: "Amenities",
      segments: "Target segments",
      experiences: "Experiences",
      guardrails: "Pricing guardrails",
      importData: "Import data",
      importHint: "Upload your files — we'll extract rooms, occupancy, rates, and guest data automatically.",
      dpaNotice: "A data processing agreement is required before importing guest data.",
    },
    import: {
      title: "Import data",
      subtitle: "Upload your hotel files and we'll extract the data automatically",
      dropHere: "Drop files here",
      browse: "Browse files",
      formats: "Excel, CSV, Word, PDF, or text",
      maxSize: "Max 10 MB per file",
      uploading: "Uploading…",
      parsing: "Reading your file with AI…",
      preview: "Preview",
      confirm: "Confirm import",
      cancel: "Cancel",
      back: "Back to set-up",
      noData: "No data found in this file",
      found: "Found",
      rows: "rows",
      problems: "Problems",
      rooms: "Rooms & availability",
      occupancy: "Past occupancy (daily)",
      monthly_occupancy: "Past occupancy (monthly)",
      rates: "Rates & rules",
      guests: "Guest list",
      amenities: "Amenities",
      extras: "Extras",
      history: "Import history",
      undo: "Undo",
      deleteGuests: "Delete all guest data",
      deleteGuestsConfirm: "This will permanently delete all imported guest data. Are you sure?",
      consentMissing: "guests without marketing consent",
      duplicateEmails: "duplicate emails",
      unreadableDates: "dates could not be read",
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
      noOffer: "Nessuna offerta",
      createAnyway: "Crea un'offerta comunque",
      seeTheData: "Vedi i dati",
      whyTheseDates: "Perché queste date",
      roomsFree: "camere libere",
    },
    calendar: {
      title: "Calendario e regole",
      freeRooms: "libere",
      blocked: "Bloccato",
      events: "Eventi",
      offers: "Offerte inviate",
      schoolHoliday: "Vacanze scolastiche",
      ponte: "Ponte",
      weekend: "Fine settimana",
      rules: "Regole",
      publicRate: "Tariffa pubblica",
      lowestPrice: "Prezzo minimo",
      maxDiscount: "Sconto massimo",
      maxRooms: "Camere max/offerta",
      blackoutDates: "Date bloccate",
      bookingWindow: "Finestra prenotazione",
      offerLifetime: "Durata offerta",
      contactCooldown: "Pausa contatto",
      autoSend: "Invio automatico",
      autoWaves: "Onde automatiche",
      save: "Salva regole",
      saved: "Salvato",
      days: "giorni",
      hours: "ore",
      perNight: "/notte",
      high: "Alta",
      medium: "Media",
      low: "Bassa",
      veryLow: "Molto bassa",
    },
    results: {
      title: "Risultati",
      offersSent: "Offerte inviate",
      bookings: "Prenotazioni",
      revenue: "Ricavi",
      commission: "Commissione (15%)",
      uplift: "Incremento vs controllo",
      holdback: "Gruppo di controllo 10%",
      perOffer: "Per offerta e onda",
      bySegment: "Per segmento",
      byCity: "Per città",
      byPackage: "Per pacchetto / extra",
      backtest: "Back-test 12 mesi",
      learnings: "Cosa ha imparato il motore",
      noData: "Dati insufficienti. Invia qualche offerta e i risultati appariranno qui.",
      demoLabel: "Dati demo simulati",
      months: "mesi",
      flagged: "segnalati",
      sent: "Inviati",
      opened: "Aperti",
      clicked: "Cliccati",
      booked: "Prenotati",
      roomsLeft: "Camere rimaste",
      skipped: "Saltati",
    },
    setup: {
      title: "Impostazioni",
      comingSoon: "",
      amenities: "Servizi",
      segments: "Segmenti target",
      experiences: "Esperienze",
      guardrails: "Regole di prezzo",
      importData: "Importa dati",
      importHint: "Carica i tuoi file — estrarremo camere, occupazione, tariffe e dati ospiti automaticamente.",
      dpaNotice: "È necessario un accordo sul trattamento dei dati prima di importare dati degli ospiti.",
    },
    import: {
      title: "Importa dati",
      subtitle: "Carica i file del tuo hotel e estrarremo i dati automaticamente",
      dropHere: "Trascina i file qui",
      browse: "Sfoglia file",
      formats: "Excel, CSV, Word, PDF o testo",
      maxSize: "Max 10 MB per file",
      uploading: "Caricamento…",
      parsing: "Lettura del file con IA…",
      preview: "Anteprima",
      confirm: "Conferma importazione",
      cancel: "Annulla",
      back: "Torna alle impostazioni",
      noData: "Nessun dato trovato in questo file",
      found: "Trovati",
      rows: "righe",
      problems: "Problemi",
      rooms: "Camere e disponibilità",
      occupancy: "Occupazione passata (giornaliera)",
      monthly_occupancy: "Occupazione passata (mensile)",
      rates: "Tariffe e regole",
      guests: "Lista ospiti",
      amenities: "Servizi",
      extras: "Extra",
      history: "Storico importazioni",
      undo: "Annulla",
      deleteGuests: "Elimina tutti i dati ospiti",
      deleteGuestsConfirm: "Questo eliminerà permanentemente tutti i dati ospiti importati. Sei sicuro?",
      consentMissing: "ospiti senza consenso marketing",
      duplicateEmails: "email duplicate",
      unreadableDates: "date non leggibili",
    },
  },
};

export type Translations = TranslationStrings;

export function t(locale: Locale): Translations {
  return translations[locale];
}
