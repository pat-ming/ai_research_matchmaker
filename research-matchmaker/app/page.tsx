"use client";

import { useState, useEffect } from 'react';

// ── Types matching the FastAPI response ─────────────────────────────────────
interface PaperResult {
  title: string;
  citations: number;
  doi: string | null;
  date: string | null;
  compatibility: number;
}

interface FacultyResult {
  rank: number;
  name: string;
  department: string;
  school: string;
  profile_url: string | null;
  research_areas: string[];
  weighted_score: number;
  matches: Record<string, number>;
  papers: PaperResult[];
  recent_papers: PaperResult[];
}

// ── Constants ───────────────────────────────────────────────────────────────
const API_URL = "http://localhost:8000";

export default function Home() {
  // Department names match Qdrant payload values exactly
  const departments: Record<string, string[]> = {
    'McKelvey': [
      'Computer Science & Engineering',
      'Biomedical Engineering',
      'Electrical & Systems Engineering',
      'Energy, Environmental & Chemical Engineering',
      'Mechanical Engineering & Materials Science'
    ],
    'Arts & Sciences': [
      'Physics', 'Chemistry', 'Biology', 'Mathematics & Statistics',
      'Earth, Environmental & Planetary Sciences',
      'Institute of Materials Science & Engineering',
      'Philosophy-Neuroscience-Psychology',
      'Psychological & Brain Sciences'
    ],
    'WashU Med': [
      'Genetics', 'Neuroscience', 'Biochemistry & Molecular Biophysics',
      'Cell Biology & Physiology', 'Developmental Biology', 'Molecular Microbiology'
    ]
  };

  const schoolDescriptions: Record<string, string> = {
    'McKelvey': 'School of Engineering',
    'Arts & Sciences': 'Arts & Sciences',
    'WashU Med': 'School of Medicine',
  };

  // ── State ───────────────────────────────────────────────────────────────────
  const [isStudent, setIsStudent] = useState<boolean | null>(null);
  const [selectedSchool, setSelectedSchool] = useState<string | null>(null);
  const [selectedDepts, setSelectedDepts] = useState<string[]>([]);
  const [researchInterest, setResearchInterest] = useState('');
  const [darkMode, setDarkMode] = useState(false);

  // Search state
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<FacultyResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  useEffect(() => {
    if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setDarkMode(true);
    }
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);

  const toggleDept = (dept: string) => {
    if (selectedDepts.includes(dept)) {
      setSelectedDepts(selectedDepts.filter(d => d !== dept));
    } else {
      setSelectedDepts([...selectedDepts, dept]);
    }
  };

  // ── Search handler ────────────────────────────────────────────────────────
  const handleSearch = async () => {
    setLoading(true);
    setError(null);
    setResults([]);
    setHasSearched(true);

    try {
      const resp = await fetch(`${API_URL}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: researchInterest,
          school: selectedSchool,
          departments: selectedDepts,
          limit: 10,
          papers_per_faculty: 5,
        }),
      });

      if (!resp.ok) {
        throw new Error(`Server error: ${resp.status}`);
      }

      const data = await resp.json();
      setResults(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect to search server");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="relative min-h-screen flex flex-col items-center px-4 py-16 transition-colors duration-500 overflow-hidden">

      {/* Floating gradient blobs */}
      <div className="gradient-blob blob-1" />
      <div className="gradient-blob blob-2" />
      <div className="gradient-blob blob-3" />
      <div className="gradient-blob blob-4" />
      <div className="gradient-blob blob-5" />

      {/* Flowy outline rings */}
      <div className="flowy-ring ring-1" />
      <div className="flowy-ring ring-2" />
      <div className="flowy-ring ring-3" />
      <div className="flowy-ring ring-4" />
      <div className="flowy-ring ring-5" />
      <div className="flowy-ring ring-6" />

      {/* Dark mode toggle */}
      <button
        onClick={() => setDarkMode(!darkMode)}
        className="fixed top-6 right-6 p-2.5 rounded-full bg-white/70 dark:bg-gray-800/70 backdrop-blur-md shadow-lg border border-rose-900/10 dark:border-rose-400/15 hover:scale-110 active:scale-95 transition-all duration-200 z-50 cursor-pointer"
        aria-label="Toggle dark mode"
      >
        {darkMode ? (
          <svg className="w-5 h-5 text-amber-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clipRule="evenodd" />
          </svg>
        ) : (
          <svg className="w-5 h-5 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
            <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
          </svg>
        )}
      </button>

      <div className="relative z-10 w-full max-w-3xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <p className="inline-block text-xs font-medium tracking-widest uppercase text-rose-900/50 dark:text-rose-300/50 bg-rose-900/5 dark:bg-rose-400/10 px-4 py-1.5 rounded-full mb-6 border border-rose-900/10 dark:border-rose-400/15">
            Washington University in St. Louis
          </p>
          <h1 className="text-6xl sm:text-7xl font-extrabold tracking-tight text-rose-900 dark:text-rose-400">
            STEM Research Matchmaker
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-4 text-lg font-light">
            Who&apos;s your best STEM Faculty match?
          </p>
        </div>

        {/* Main card */}
        <div className="bg-white/80 dark:bg-gray-800/50 backdrop-blur-xl rounded-2xl shadow-xl border border-rose-900/8 dark:border-rose-400/10 p-8 sm:p-10 transition-all duration-300">

          {/* Section 1: Enrollment */}
          <section className="mb-10">
            <label className="block font-semibold text-lg text-gray-800 dark:text-gray-100 mb-4">
              Are you currently enrolled at WashU?
            </label>
            <div className="flex gap-3">
              {[true, false].map((val) => (
                <button
                  key={val.toString()}
                  onClick={() => setIsStudent(val)}
                  className={`px-7 py-2.5 rounded-full border font-medium transition-all duration-200 cursor-pointer ${
                    isStudent === val
                      ? "bg-rose-900 dark:bg-rose-700 border-rose-900 dark:border-rose-700 text-white shadow-lg shadow-rose-900/20 dark:shadow-rose-900/30"
                      : "bg-white/60 dark:bg-gray-700/40 border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-300 hover:border-rose-300 dark:hover:border-rose-700 hover:text-gray-700 dark:hover:text-gray-100"
                  }`}
                >
                  {val ? "Yes, I am" : "No, not yet"}
                </button>
              ))}
            </div>
          </section>

          {/* Section 2: School */}
          {isStudent !== null && (
            <section className="mb-10 animate-fade-in-up">
              <label className="block font-semibold text-lg text-gray-800 dark:text-gray-100 mb-4">
                Which school are you interested in?
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {Object.keys(departments).map((school) => (
                  <button
                    key={school}
                    onClick={() => {
                      setSelectedSchool(school);
                      setSelectedDepts([]);
                      setResults([]);
                      setHasSearched(false);
                    }}
                    className={`p-5 rounded-xl border text-center transition-all duration-200 cursor-pointer ${
                      selectedSchool === school
                        ? "bg-rose-50 dark:bg-rose-900/20 border-rose-400 dark:border-rose-600 shadow-md shadow-rose-200/40 dark:shadow-rose-900/20"
                        : "bg-white/50 dark:bg-gray-700/20 border-gray-200 dark:border-gray-600 hover:border-rose-300 dark:hover:border-rose-700 hover:shadow-sm hover:bg-white/80 dark:hover:bg-gray-700/40"
                    }`}
                  >
                    <span className={`block font-semibold ${
                      selectedSchool === school
                        ? "text-rose-900 dark:text-rose-300"
                        : "text-gray-800 dark:text-gray-200"
                    }`}>
                      {school}
                    </span>
                    <span className={`block text-xs mt-1 ${
                      selectedSchool === school
                        ? "text-rose-700/60 dark:text-rose-400/50"
                        : "text-gray-400 dark:text-gray-500"
                    }`}>
                      {schoolDescriptions[school]}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}

          {/* Section 3: Departments */}
          {selectedSchool && (
            <section className="mb-10 animate-fade-in-up">
              <label className="block font-semibold text-lg text-gray-800 dark:text-gray-100 mb-4">
                Select departments of interest:
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {departments[selectedSchool].map((dept) => (
                  <div
                    key={dept}
                    onClick={() => toggleDept(dept)}
                    className={`flex items-center p-3.5 rounded-xl border cursor-pointer transition-all duration-150 ${
                      selectedDepts.includes(dept)
                        ? "bg-rose-50 dark:bg-rose-900/15 border-rose-200 dark:border-rose-800/50 shadow-sm"
                        : "bg-white/40 dark:bg-gray-700/15 border-gray-100 dark:border-gray-700/40 hover:bg-white/70 dark:hover:bg-gray-700/30 hover:border-gray-200 dark:hover:border-gray-600"
                    }`}
                  >
                    <div className={`w-5 h-5 rounded-md border-2 mr-3 flex items-center justify-center flex-shrink-0 transition-all duration-150 ${
                      selectedDepts.includes(dept)
                        ? "bg-rose-800 border-rose-800 dark:bg-rose-600 dark:border-rose-600"
                        : "border-gray-300 dark:border-gray-500"
                    }`}>
                      {selectedDepts.includes(dept) && (
                        <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </div>
                    <span className={`text-sm ${
                      selectedDepts.includes(dept)
                        ? "font-medium text-rose-900 dark:text-rose-300"
                        : "text-gray-600 dark:text-gray-300"
                    }`}>
                      {dept}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Section 4: Research Interest */}
          {selectedDepts.length > 0 && (
            <section className="mb-10 animate-fade-in-up">
              <label className="block font-semibold text-lg text-gray-800 dark:text-gray-100 mb-2">
                Describe your research interest:
              </label>
              <p className="text-sm text-gray-400 dark:text-gray-500 mb-4">
                In 1-2 sentences, tell us what excites you.
              </p>
              <textarea
                value={researchInterest}
                onChange={(e) => setResearchInterest(e.target.value)}
                placeholder="e.g. I'm interested in applying machine learning to protein folding and drug discovery..."
                maxLength={300}
                rows={3}
                className="w-full rounded-xl border border-gray-200 dark:border-gray-600 bg-white/60 dark:bg-gray-700/30 px-4 py-3 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-rose-400 dark:focus:border-rose-500 focus:ring-2 focus:ring-rose-400/20 dark:focus:ring-rose-500/20 transition-all duration-200 resize-none"
              />
              <div className="flex items-center justify-between mt-3">
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  {researchInterest.length}/300
                </p>
                <button
                  onClick={handleSearch}
                  disabled={researchInterest.trim().length === 0 || loading}
                  className={`px-6 py-2 rounded-full font-medium text-sm transition-all duration-200 cursor-pointer ${
                    researchInterest.trim().length > 0 && !loading
                      ? "bg-rose-900 dark:bg-rose-700 text-white shadow-md shadow-rose-900/20 dark:shadow-rose-900/30 hover:bg-rose-800 dark:hover:bg-rose-600 active:scale-95"
                      : "bg-gray-200 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed"
                  }`}
                >
                  {loading ? "Searching..." : "Find Matches"}
                </button>
              </div>
            </section>
          )}

          {/* Error */}
          {error && (
            <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/50 rounded-xl text-red-700 dark:text-red-300 text-sm animate-fade-in-up">
              {error}
            </div>
          )}

          {/* Loading spinner */}
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 animate-fade-in-up">
              <div className="w-10 h-10 border-3 border-rose-200 dark:border-rose-800 border-t-rose-900 dark:border-t-rose-400 rounded-full animate-spin" />
              <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
                Searching faculty & fetching papers...
              </p>
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                This may take a minute for ORCID lookups
              </p>
            </div>
          )}
        </div>

      </div>

      {/* ── Results (wider container) ─────────────────────────────────────── */}
      {!loading && hasSearched && results.length > 0 && (
        <div className="relative z-10 w-full max-w-7xl mx-auto px-3 mt-8 space-y-4 animate-fade-in-up">
          <h2 className="text-2xl font-bold text-rose-900 dark:text-rose-400 mb-2">
            Your Top Faculty Matches
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
            {results.length} faculty found — ranked by research compatibility
          </p>

          {results.map((fac) => (
            <div
              key={fac.rank}
              className="bg-white dark:bg-gray-800 backdrop-blur-xl rounded-2xl shadow-lg border border-rose-900/8 dark:border-rose-400/10 p-6 sm:p-8 transition-all duration-300 hover:shadow-xl"
            >
              {/* Faculty header */}
              <div className="flex items-start justify-between gap-4 mb-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-rose-900 dark:bg-rose-700 text-white text-sm font-bold flex-shrink-0">
                      {fac.rank}
                    </span>
                    <h3 className="text-xl font-bold text-gray-900 dark:text-gray-50 truncate">
                      {fac.name}
                    </h3>
                  </div>
                  <p className="text-sm text-gray-500 dark:text-gray-400 ml-11">
                    {fac.department} — {fac.school}
                  </p>
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="text-2xl font-bold text-rose-900 dark:text-rose-400">
                    {(fac.weighted_score * 100).toFixed(1)}%
                  </div>
                  <div className="text-xs text-gray-400 dark:text-gray-500">match</div>
                </div>
              </div>

              {/* Profile link */}
              {fac.profile_url && (
                <a
                  href={fac.profile_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm text-rose-700 dark:text-rose-400 hover:text-rose-900 dark:hover:text-rose-300 transition-colors ml-11 mb-3"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                  </svg>
                  View Profile
                </a>
              )}

              {/* Research areas */}
              {fac.research_areas.length > 0 && (
                <div className="flex flex-wrap gap-1.5 ml-11 mb-4">
                  {fac.research_areas.map((area) => (
                    <span
                      key={area}
                      className="inline-block bg-rose-50 dark:bg-rose-900/20 text-rose-800 dark:text-rose-300 text-xs font-medium px-2.5 py-1 rounded-full border border-rose-200/60 dark:border-rose-800/40"
                    >
                      {area}
                    </span>
                  ))}
                </div>
              )}

              {/* Vector match breakdown */}
              <div className="flex gap-3 ml-11 mb-5">
                {Object.entries(fac.matches).map(([vecName, score]) => (
                  <div key={vecName} className="text-xs text-gray-400 dark:text-gray-500">
                    <span className="capitalize">{vecName.replace('_', ' ')}</span>:{' '}
                    <span className="font-medium text-gray-600 dark:text-gray-300">
                      {(score * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>

              {/* Papers — two columns */}
              {(fac.papers.length > 0 || fac.recent_papers.length > 0) ? (
                <div className="ml-11 grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Top Papers (by citations) */}
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-3">
                      Top Papers
                    </h4>
                    <div className="space-y-2.5">
                      {fac.papers.map((paper, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-100/60 dark:border-gray-700/30"
                        >
                          <div className="flex-shrink-0 w-14 text-center">
                            <div className="text-sm font-bold text-rose-900 dark:text-rose-400">
                              {(paper.compatibility * 100).toFixed(0)}%
                            </div>
                            <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full mt-1 overflow-hidden">
                              <div
                                className="h-full bg-rose-500 dark:bg-rose-400 rounded-full transition-all duration-500"
                                style={{ width: `${Math.max(paper.compatibility * 100, 5)}%` }}
                              />
                            </div>
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-gray-800 dark:text-gray-200 leading-snug">
                              {paper.title}
                            </p>
                            <div className="flex items-center gap-3 mt-1">
                              <span className="text-xs text-gray-400 dark:text-gray-500">
                                {paper.citations} citations
                              </span>
                              {paper.doi && (
                                <a href={paper.doi} target="_blank" rel="noopener noreferrer" className="text-xs text-rose-600 dark:text-rose-400 hover:underline">DOI</a>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Recent Papers (by date) */}
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-3">
                      Recent Papers
                    </h4>
                    <div className="space-y-2.5">
                      {fac.recent_papers.map((paper, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-100/60 dark:border-gray-700/30"
                        >
                          <div className="flex-shrink-0 w-14 text-center">
                            <div className="text-sm font-bold text-rose-900 dark:text-rose-400">
                              {(paper.compatibility * 100).toFixed(0)}%
                            </div>
                            <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full mt-1 overflow-hidden">
                              <div
                                className="h-full bg-rose-500 dark:bg-rose-400 rounded-full transition-all duration-500"
                                style={{ width: `${Math.max(paper.compatibility * 100, 5)}%` }}
                              />
                            </div>
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-gray-800 dark:text-gray-200 leading-snug">
                              {paper.title}
                            </p>
                            <div className="flex items-center gap-3 mt-1">
                              {paper.date && (
                                <span className="text-xs text-gray-400 dark:text-gray-500">
                                  {paper.date}
                                </span>
                              )}
                              <span className="text-xs text-gray-400 dark:text-gray-500">
                                {paper.citations} citations
                              </span>
                              {paper.doi && (
                                <a href={paper.doi} target="_blank" rel="noopener noreferrer" className="text-xs text-rose-600 dark:text-rose-400 hover:underline">DOI</a>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <p className="ml-11 text-xs text-gray-400 dark:text-gray-500 italic">
                  No ORCID / papers found for this faculty member
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* No results */}
      {!loading && hasSearched && results.length === 0 && !error && (
        <div className="relative z-10 mt-8 text-center py-12 animate-fade-in-up">
          <p className="text-gray-500 dark:text-gray-400">No faculty matches found. Try broadening your search.</p>
        </div>
      )}
    </main>
  );
}
