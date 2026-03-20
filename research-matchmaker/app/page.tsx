"use client";

import { useState, useEffect } from 'react';

export default function Home() {
  const departments: Record<string, string[]> = {
    'McKelvey': [
      'Computer Science and Engineering',
      'Biomedical Engineering',
      'Electrical Systems and Engineering',
      'Energy, Environmental & Chemical Engineering',
      'Mechanical Engineering & Materials Science'
    ],
    'Arts & Sciences': [
      'Physics', 'Chemistry', 'Biology', 'Mathematics',
      'Earth, Environmental, and Planetary Sciences',
      'Institute of Material Science Engineering',
      'Philosophy-Neuroscience-Psychology',
      'Psychological & Brain Sciences'
    ],
    'WashU Med': [
      'Genetics', 'Neuroscience', 'Biochem',
      'Cell Biology', 'Developmental Biology', 'Microbiology'
    ]
  };

  const schoolDescriptions: Record<string, string> = {
    'McKelvey': 'School of Engineering',
    'Arts & Sciences': 'Arts & Sciences',
    'WashU Med': 'School of Medicine',
  };

  const [isStudent, setIsStudent] = useState<boolean | null>(null);
  const [selectedSchool, setSelectedSchool] = useState<string | null>(null);
  const [selectedDepts, setSelectedDepts] = useState<string[]>([]);
  const [darkMode, setDarkMode] = useState(false);

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

  return (
    <main className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-gray-50 to-red-50/30 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950 px-4 py-12 transition-colors duration-500">

      {/* Dark mode toggle */}
      <button
        onClick={() => setDarkMode(!darkMode)}
        className="fixed top-5 right-5 p-2.5 rounded-full bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm shadow-lg border border-gray-200/60 dark:border-gray-700/60 hover:scale-110 active:scale-95 transition-all duration-200 z-50 cursor-pointer"
        aria-label="Toggle dark mode"
      >
        {darkMode ? (
          <svg className="w-5 h-5 text-amber-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clipRule="evenodd" />
          </svg>
        ) : (
          <svg className="w-5 h-5 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
            <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
          </svg>
        )}
      </button>

      <div className="w-full max-w-3xl">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-5xl sm:text-6xl font-extrabold tracking-tight bg-gradient-to-r from-red-700 to-red-600 dark:from-red-500 dark:to-red-400 bg-clip-text text-transparent">
            WashU Research Matchmaker
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-4 text-lg">
            Find your laboratory home at Washington University in St. Louis.
          </p>
        </div>

        {/* Main card */}
        <div className="bg-white dark:bg-gray-800/70 backdrop-blur-sm rounded-2xl shadow-xl shadow-gray-200/50 dark:shadow-black/20 border border-gray-100 dark:border-gray-700/60 p-8 sm:p-10 transition-colors duration-300">

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
                  className={`px-7 py-2.5 rounded-full border-2 font-medium transition-all duration-200 cursor-pointer ${
                    isStudent === val
                      ? "bg-red-700 border-red-700 text-white shadow-md shadow-red-200/50 dark:shadow-red-900/30"
                      : "bg-white dark:bg-gray-700/50 border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-300 hover:border-red-300 dark:hover:border-red-500 hover:text-gray-700 dark:hover:text-gray-100"
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
                    }}
                    className={`p-5 rounded-xl border-2 text-center transition-all duration-200 cursor-pointer ${
                      selectedSchool === school
                        ? "bg-red-50 dark:bg-red-900/20 border-red-500 dark:border-red-500 shadow-md shadow-red-100/50 dark:shadow-red-900/20"
                        : "bg-gray-50/50 dark:bg-gray-700/30 border-gray-200 dark:border-gray-600 hover:border-red-300 dark:hover:border-red-500/60 hover:shadow-sm"
                    }`}
                  >
                    <span className={`block font-semibold ${
                      selectedSchool === school
                        ? "text-red-800 dark:text-red-300"
                        : "text-gray-800 dark:text-gray-200"
                    }`}>
                      {school}
                    </span>
                    <span className={`block text-xs mt-1 ${
                      selectedSchool === school
                        ? "text-red-600/70 dark:text-red-400/60"
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
                        ? "bg-red-50 dark:bg-red-900/15 border-red-200 dark:border-red-800/60 shadow-sm"
                        : "bg-white dark:bg-gray-700/20 border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/40 hover:border-gray-200 dark:hover:border-gray-600"
                    }`}
                  >
                    <div className={`w-5 h-5 rounded-md border-2 mr-3 flex items-center justify-center flex-shrink-0 transition-all duration-150 ${
                      selectedDepts.includes(dept)
                        ? "bg-red-600 border-red-600 dark:bg-red-500 dark:border-red-500"
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
                        ? "font-medium text-red-900 dark:text-red-300"
                        : "text-gray-600 dark:text-gray-300"
                    }`}>
                      {dept}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Summary */}
          {selectedDepts.length > 0 && (
            <div className="p-6 bg-gradient-to-br from-gray-900 to-gray-800 dark:from-gray-700/80 dark:to-gray-800/80 rounded-xl text-white shadow-lg animate-fade-in-up">
              <h3 className="text-red-400 font-bold uppercase tracking-widest text-xs mb-4">
                Your Profile Summary
              </h3>
              <div className="space-y-2 text-sm">
                <p className="flex justify-between items-center border-b border-gray-700/50 pb-2">
                  <span className="text-gray-400">Status</span>
                  <span className="font-medium">{isStudent ? "Current Student" : "External User"}</span>
                </p>
                <p className="flex justify-between items-center border-b border-gray-700/50 pb-2">
                  <span className="text-gray-400">School</span>
                  <span className="font-medium">{selectedSchool}</span>
                </p>
                <div className="pt-1">
                  <span className="text-gray-400 text-xs">Departments of Interest</span>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {selectedDepts.map((dept) => (
                      <span key={dept} className="inline-block bg-red-500/20 text-red-300 text-xs font-medium px-3 py-1 rounded-full border border-red-500/30">
                        {dept}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-gray-400 dark:text-gray-600 text-xs mt-8">
          Washington University in St. Louis
        </p>
      </div>
    </main>
  );
}
