import { useState, useEffect, useCallback } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import axios from "axios";
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";
import 'katex/dist/katex.min.css';
import { InlineMath, BlockMath } from 'react-katex';
import { 
  FilePdf, 
  Upload, 
  CheckCircle, 
  XCircle, 
  Clock, 
  CaretRight,
  Image as ImageIcon,
  Table,
  ChartLine,
  Stack,
  MagnifyingGlass,
  Funnel,
  ArrowClockwise,
  Eye,
  Check,
  X,
  Tag,
  Medal,
  ListChecks,
  BookOpen,
  CaretDown,
  Plus,
  LightbulbFilament
} from "@phosphor-icons/react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// ============ Helper Functions ============
const renderLatex = (text, latex) => {
  if (!latex) return <span className="whitespace-pre-wrap">{text}</span>;
  
  try {
    // Handle tables - render as HTML table
    if (latex.includes('\\begin{tabular}') || latex.includes('\\hline')) {
      try {
        return <BlockMath math={latex} />;
      } catch {
        // Fallback: show clean text for tables
        return <span className="whitespace-pre-wrap">{text}</span>;
      }
    }

    // Check if the content has explicit LaTeX delimiters \( \) or \[ \]
    const hasDelimiters = /\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]/s.test(latex);
    
    if (hasDelimiters) {
      const parts = latex.split(/(\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\])/g);
      return (
        <span>
          {parts.map((part, idx) => {
            if (part.startsWith('\\(') && part.endsWith('\\)')) {
              const math = part.slice(2, -2);
              try { return <InlineMath key={idx} math={math} />; } catch { return <span key={idx}>{math}</span>; }
            } else if (part.startsWith('\\[') && part.endsWith('\\]')) {
              const math = part.slice(2, -2);
              try { return <BlockMath key={idx} math={math} />; } catch { return <span key={idx}>{math}</span>; }
            }
            return <span key={idx}>{part}</span>;
          })}
        </span>
      );
    }
    
    // Check if content has LaTeX commands that KaTeX can render
    const hasLatexCmds = /\\(text|frac|tfrac|sqrt|cdot|times|div|pm|leq|geq|neq|approx|rightarrow|begin|end|quad|displaystyle)/i.test(latex);
    
    if (hasLatexCmds) {
      try {
        return <BlockMath math={latex} />;
      } catch {
        return <span className="whitespace-pre-wrap">{text}</span>;
      }
    }
    
    // If latex has long english words, show plain text
    const hasLongWords = /(?<!\\)[a-zA-Z]{5,}/.test(latex);
    if (hasLongWords) {
      return <span className="whitespace-pre-wrap">{text}</span>;
    }
    
    // Simple math expression
    try {
      return <InlineMath math={latex} />;
    } catch {
      return <span className="whitespace-pre-wrap">{text}</span>;
    }
  } catch (e) {
    return <span className="whitespace-pre-wrap">{text}</span>;
  }
};

// ============ Components ============

const StatusTag = ({ status }) => {
  const statusClasses = {
    draft: "status-draft",
    processing: "status-processing",
    "needs_review": "status-needs-review",
    approved: "status-approved",
    extracted: "status-extracted",
    completed: "status-approved",
    failed: "status-needs-review",
    pending: "status-processing",
    linked: "status-approved"
  };
  
  return (
    <span data-testid={`status-tag-${status}`} className={`status-tag ${statusClasses[status] || "status-draft"}`}>
      {status?.replace("_", " ")}
    </span>
  );
};

const DifficultyBadge = ({ difficulty, onChange }) => {
  const colors = {
    bronze: "bg-amber-100 border-amber-600 text-amber-800",
    silver: "bg-slate-100 border-slate-500 text-slate-800",
    gold: "bg-yellow-100 border-yellow-600 text-yellow-800"
  };
  
  if (onChange) {
    return (
      <select
        data-testid="difficulty-select"
        value={difficulty || ""}
        onChange={(e) => onChange(e.target.value)}
        className={`text-xs px-2 py-1 border font-mono uppercase ${colors[difficulty] || "bg-white border-black"}`}
      >
        <option value="">Set Difficulty</option>
        <option value="bronze">Bronze</option>
        <option value="silver">Silver</option>
        <option value="gold">Gold</option>
      </select>
    );
  }
  
  if (!difficulty) return null;
  
  return (
    <span className={`text-xs px-2 py-1 border font-mono uppercase ${colors[difficulty]}`}>
      <Medal size={12} className="inline mr-1" weight="fill" />
      {difficulty}
    </span>
  );
};

const TopicTags = ({ topics, allTopics, onChange }) => {
  const [showDropdown, setShowDropdown] = useState(false);
  
  if (onChange) {
    return (
      <div className="relative">
        <div className="flex flex-wrap gap-1 mb-2">
          {topics?.map((topic) => (
            <span 
              key={topic}
              className="text-xs px-2 py-1 border border-blue-600 bg-blue-50 text-blue-800 flex items-center gap-1"
            >
              {topic}
              <button 
                onClick={() => onChange(topics.filter(t => t !== topic))}
                className="hover:text-red-600"
              >
                <X size={10} weight="bold" />
              </button>
            </span>
          ))}
          <button
            data-testid="add-topic-btn"
            onClick={() => setShowDropdown(!showDropdown)}
            className="text-xs px-2 py-1 border border-dashed border-black hover:bg-slate-100"
          >
            <Plus size={10} className="inline" /> Add
          </button>
        </div>
        {showDropdown && (
          <div className="absolute z-10 bg-white border border-black shadow-lg max-h-48 overflow-auto w-64">
            {Object.entries(allTopics || {}).map(([category, categoryTopics]) => (
              <div key={category}>
                <div className="px-2 py-1 bg-slate-100 text-xs font-bold uppercase tracking-wider">
                  {category}
                </div>
                {categoryTopics.map((t) => (
                  <button
                    key={t.name}
                    onClick={() => {
                      if (!topics?.includes(t.name)) {
                        onChange([...(topics || []), t.name]);
                      }
                      setShowDropdown(false);
                    }}
                    disabled={topics?.includes(t.name)}
                    className="block w-full text-left px-3 py-1 text-xs hover:bg-slate-50 disabled:opacity-50"
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
  
  if (!topics?.length) return null;
  
  return (
    <div className="flex flex-wrap gap-1">
      {topics.map((topic) => (
        <span 
          key={topic}
          className="text-xs px-2 py-1 border border-slate-400 bg-slate-50"
        >
          <Tag size={10} className="inline mr-1" />
          {topic}
        </span>
      ))}
    </div>
  );
};

const ProgressBar = ({ value, max }) => {
  const percent = max > 0 ? (value / max) * 100 : 0;
  return (
    <div className="progress-bar w-full" data-testid="progress-bar">
      <div className="progress-bar-fill" style={{ width: `${percent}%` }} />
    </div>
  );
};

// ============ PDF Upload Zone ============
const PDFUploadZone = ({ paperId, onUploadComplete, type = "paper" }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && droppedFile.type === "application/pdf") {
      setFile(droppedFile);
    } else {
      toast.error("Please drop a PDF file");
    }
  };

  const handleFileSelect = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  const handleUpload = async () => {
    if (!file || !paperId) return;
    
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    const endpoint = type === "markscheme" 
      ? `${API}/papers/${paperId}/mark-scheme/upload`
      : `${API}/papers/${paperId}/upload`;

    try {
      const response = await axios.post(endpoint, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      toast.success(`${type === "markscheme" ? "Mark scheme" : "PDF"} uploaded! Extraction started.`);
      onUploadComplete(response.data.job_id || response.data.mark_scheme_id);
      setFile(null);
    } catch (error) {
      toast.error("Upload failed: " + (error.response?.data?.detail || error.message));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-4 border-b border-black">
      <div className="text-xs tracking-widest uppercase font-bold mb-2">
        {type === "markscheme" ? "Mark Scheme" : "Question Paper"}
      </div>
      <div
        data-testid={`${type}-upload-zone`}
        className={`dropzone ${isDragging ? "active" : ""} p-6`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => document.getElementById(`${type}-input`).click()}
      >
        <input
          id={`${type}-input`}
          data-testid={`${type}-file-input`}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleFileSelect}
        />
        {file ? (
          <div className="flex flex-col items-center gap-2">
            <FilePdf size={32} weight="duotone" />
            <p className="font-mono text-xs">{file.name}</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <Upload size={32} weight="duotone" />
            <p className="font-mono text-xs">Drop {type === "markscheme" ? "mark scheme" : "PDF"}</p>
          </div>
        )}
      </div>
      
      {file && (
        <button
          data-testid={`upload-${type}-btn`}
          onClick={handleUpload}
          disabled={uploading || !paperId}
          className="btn-primary w-full mt-2 text-sm py-2 disabled:opacity-50"
        >
          {uploading ? "Uploading..." : "Extract"}
        </button>
      )}
    </div>
  );
};

// ============ Paper Form ============
const PaperForm = ({ onPaperCreated }) => {
  const [formData, setFormData] = useState({
    board: "AQA",
    qualification: "GCSE",
    subject: "Mathematics",
    paper_number: "1",
    tier: "Higher",
    session: "June",
    exam_year: 2024
  });
  const [creating, setCreating] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      const response = await axios.post(`${API}/papers`, formData);
      toast.success("Paper created!");
      onPaperCreated(response.data);
    } catch (error) {
      toast.error("Failed to create paper");
    } finally {
      setCreating(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="p-4 border-b border-black">
      <h3 className="font-sans text-base font-semibold mb-3">New Paper</h3>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs tracking-widest uppercase font-bold block mb-1">Board</label>
          <select
            data-testid="paper-board-select"
            value={formData.board}
            onChange={(e) => setFormData({...formData, board: e.target.value})}
            className="w-full border border-black p-2 bg-white text-sm"
          >
            <option value="AQA">AQA</option>
            <option value="Edexcel">Edexcel</option>
            <option value="OCR">OCR</option>
          </select>
        </div>
        <div>
          <label className="text-xs tracking-widest uppercase font-bold block mb-1">Year</label>
          <input
            data-testid="paper-year-input"
            type="number"
            value={formData.exam_year}
            onChange={(e) => setFormData({...formData, exam_year: parseInt(e.target.value)})}
            className="w-full border border-black p-2 text-sm"
          />
        </div>
        <div>
          <label className="text-xs tracking-widest uppercase font-bold block mb-1">Paper</label>
          <select
            data-testid="paper-number-select"
            value={formData.paper_number}
            onChange={(e) => setFormData({...formData, paper_number: e.target.value})}
            className="w-full border border-black p-2 bg-white text-sm"
          >
            <option value="1">Paper 1</option>
            <option value="2">Paper 2</option>
            <option value="3">Paper 3</option>
          </select>
        </div>
        <div>
          <label className="text-xs tracking-widest uppercase font-bold block mb-1">Tier</label>
          <select
            data-testid="paper-tier-select"
            value={formData.tier}
            onChange={(e) => setFormData({...formData, tier: e.target.value})}
            className="w-full border border-black p-2 bg-white text-sm"
          >
            <option value="Higher">Higher</option>
            <option value="Foundation">Foundation</option>
          </select>
        </div>
      </div>
      <button 
        data-testid="create-paper-btn"
        type="submit" 
        disabled={creating}
        className="btn-primary w-full mt-3 text-sm py-2"
      >
        {creating ? "Creating..." : "Create Paper"}
      </button>
    </form>
  );
};

// ============ Extraction Status ============
const ExtractionStatus = ({ jobId, onComplete }) => {
  const [job, setJob] = useState(null);

  useEffect(() => {
    if (!jobId) return;
    
    const pollStatus = async () => {
      try {
        const response = await axios.get(`${API}/extraction-jobs/${jobId}`);
        setJob(response.data);
        
        if (response.data.status === "completed") {
          onComplete();
        } else if (response.data.status === "failed") {
          toast.error("Extraction failed: " + (response.data.error_message || "Unknown error"));
        }
      } catch (error) {
        console.error("Failed to poll status:", error);
      }
    };

    pollStatus();
    const interval = setInterval(pollStatus, 2000);
    
    return () => clearInterval(interval);
  }, [jobId, onComplete]);

  if (!job) return null;

  return (
    <div data-testid="extraction-status" className="p-4 border-b border-black bg-slate-50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs tracking-widest uppercase font-bold">Extraction</span>
        <StatusTag status={job.status} />
      </div>
      <ProgressBar value={job.processed_pages} max={job.total_pages} />
      <div className="flex justify-between mt-2 text-xs text-slate-600">
        <span>Pages: {job.processed_pages}/{job.total_pages}</span>
        <span>Questions: {job.questions_found}</span>
        <span>Images: {job.images_extracted}</span>
      </div>
    </div>
  );
};

// ============ Question List ============
const QuestionList = ({ questions, selectedId, onSelect }) => {
  const [filter, setFilter] = useState("all");
  const [topicFilter, setTopicFilter] = useState("");
  const [difficultyFilter, setDifficultyFilter] = useState("");
  
  const filteredQuestions = questions.filter(q => {
    if (filter !== "all" && q.status !== filter) return false;
    if (topicFilter && !q.topics?.includes(topicFilter)) return false;
    if (difficultyFilter && q.difficulty !== difficultyFilter) return false;
    return true;
  });

  // Get unique topics from questions
  const uniqueTopics = [...new Set(questions.flatMap(q => q.topics || []))];

  return (
    <div className="h-full flex flex-col">
      {/* Filter bar */}
      <div className="p-3 border-b border-black space-y-2">
        <div className="flex items-center gap-2">
          <Funnel size={14} weight="bold" />
          <select
            data-testid="question-filter-select"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="border border-black px-2 py-1 text-xs bg-white flex-1"
          >
            <option value="all">All ({questions.length})</option>
            <option value="draft">Draft</option>
            <option value="needs_review">Needs Review</option>
            <option value="approved">Approved</option>
          </select>
        </div>
        <div className="flex gap-2">
          <select
            data-testid="topic-filter-select"
            value={topicFilter}
            onChange={(e) => setTopicFilter(e.target.value)}
            className="border border-black px-2 py-1 text-xs bg-white flex-1"
          >
            <option value="">All Topics</option>
            {uniqueTopics.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <select
            data-testid="difficulty-filter-select"
            value={difficultyFilter}
            onChange={(e) => setDifficultyFilter(e.target.value)}
            className="border border-black px-2 py-1 text-xs bg-white flex-1"
          >
            <option value="">All Levels</option>
            <option value="bronze">Bronze</option>
            <option value="silver">Silver</option>
            <option value="gold">Gold</option>
          </select>
        </div>
      </div>
      
      {/* Question rows */}
      <div className="flex-1 overflow-auto">
        {filteredQuestions.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            <Stack size={48} className="mx-auto mb-4" />
            <p className="text-sm">No questions found</p>
          </div>
        ) : (
              filteredQuestions.map((question) => (
            <div
              key={question.id}
              data-testid={`question-row-${question.question_number}`}
              onClick={() => onSelect(question)}
              className={`p-3 border-b border-black cursor-pointer transition-colors ${
                selectedId === question.id ? "bg-slate-100" : "hover:bg-slate-50"
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-sans font-bold text-base">Q{question.question_number}</span>
                  {question.ge_id && (
                    <span className="text-xs font-mono px-1 border border-blue-800 bg-blue-50 text-blue-800">{question.ge_id}</span>
                  )}
                  <div className="flex gap-1">
                    {question.has_diagram && (
                      <span title="Has diagram" className="p-1 border border-slate-400">
                        <ChartLine size={12} />
                      </span>
                    )}
                    {question.has_table && (
                      <span title="Has table" className="p-1 border border-slate-400">
                        <Table size={12} />
                      </span>
                    )}
                    {question.mark_scheme && (
                      <span title="Has mark scheme" className="p-1 border border-green-500 bg-green-50">
                        <ListChecks size={12} />
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <DifficultyBadge difficulty={question.difficulty} />
                  <StatusTag status={question.status} />
                </div>
              </div>
              <p className="text-xs text-slate-600 mt-1 line-clamp-2">{question.text}</p>
              {question.parts?.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {question.parts.map(p => (
                    <span key={p.part_label} className="text-xs font-mono px-1 border border-slate-300 bg-slate-50">
                      {p.ge_id || `(${p.part_label})`}
                    </span>
                  ))}
                </div>
              )}
              {question.topics?.length > 0 && (
                <div className="mt-2">
                  <TopicTags topics={question.topics?.slice(0, 3)} />
                </div>
              )}
              <div className="flex items-center justify-between mt-2 text-xs text-slate-500">
                <span>{question.marks ? `${question.marks} marks` : ""}</span>
                <span>{question.parts?.length || 0} parts</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

// ============ Mark Scheme Panel ============
const MarkSchemePanel = ({ question, entries }) => {
  if (!question?.mark_scheme && !entries?.length) {
    return (
      <div className="p-4 text-center text-slate-500 text-sm">
        <BookOpen size={32} className="mx-auto mb-2" />
        No mark scheme linked
      </div>
    );
  }

  return (
    <div className="border border-black">
      <div className="p-3 bg-green-50 border-b border-black">
        <span className="text-xs tracking-widest uppercase font-bold flex items-center gap-2">
          <ListChecks size={14} /> Mark Scheme
        </span>
      </div>
      
      {question?.mark_scheme && (
        <div className="p-3 border-b border-black">
          <div className="text-sm">
            {renderLatex(question.mark_scheme, question.mark_scheme_latex)}
          </div>
        </div>
      )}
      
      {entries?.map((entry, idx) => (
        <div key={entry.id || idx} className="p-3 border-b border-black last:border-b-0">
          <div className="flex items-center justify-between mb-2">
            <span className="font-bold text-sm">
              Q{entry.question_number}{entry.part_label ? `(${entry.part_label})` : ""}
            </span>
            <div className="flex gap-2 text-xs">
              {entry.method_marks > 0 && <span className="px-1 border border-blue-500 bg-blue-50">M{entry.method_marks}</span>}
              {entry.accuracy_marks > 0 && <span className="px-1 border border-green-500 bg-green-50">A{entry.accuracy_marks}</span>}
              {entry.b_marks > 0 && <span className="px-1 border border-purple-500 bg-purple-50">B{entry.b_marks}</span>}
              <span className="font-bold">[{entry.marks}]</span>
            </div>
          </div>
          <div className="text-sm mb-2">
            {renderLatex(entry.text, entry.latex)}
          </div>
          {entry.acceptable_alternatives?.length > 0 && (
            <div className="text-xs text-slate-600 mt-1">
              <strong>Also accept:</strong> {entry.acceptable_alternatives.join(", ")}
            </div>
          )}
          {entry.follow_through_notes && (
            <div className="text-xs text-blue-600 mt-1">
              <strong>FT:</strong> {entry.follow_through_notes}
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

// ============ Question Detail ============
const QuestionDetail = ({ question, onUpdate, allTopics }) => {
  const [images, setImages] = useState([]);
  const [markSchemeEntries, setMarkSchemeEntries] = useState([]);
  const [updating, setUpdating] = useState(false);
  const [showMarkScheme, setShowMarkScheme] = useState(false);
  const [showSolution, setShowSolution] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editText, setEditText] = useState("");
  const [editMarks, setEditMarks] = useState("");
  const [editParts, setEditParts] = useState([]);
  const [editSolution, setEditSolution] = useState("");

  useEffect(() => {
    if (!question) {
      setImages([]);
      setMarkSchemeEntries([]);
      return;
    }

    // Populate edit fields immediately
    setEditText(question.text || "");
    setEditMarks(question.marks?.toString() || "");
    setEditParts(question.parts?.map(p => ({ ...p })) || []);
    setEditSolution(question.solution || "");

    let mounted = true;

    // Load resources asynchronously (non-blocking)
    (async () => {
      // Load images one at a time with timeout
      if (question.images?.length > 0) {
        const loadedImages = [];
        for (const imgId of question.images) {
          if (!mounted) break;
          try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 3000);
            const response = await axios.get(`${API}/images/${imgId}`, { signal: controller.signal });
            clearTimeout(timeout);
            loadedImages.push(response.data);
            if (mounted) setImages([...loadedImages]);
          } catch {
            // Skip failed images
          }
        }
      }

      // Load mark scheme
      if (question.id && mounted) {
        try {
          const res = await axios.get(`${API}/questions/${question.id}/mark-scheme`);
          if (mounted) setMarkSchemeEntries(res.data || []);
        } catch {
          if (mounted) setMarkSchemeEntries([]);
        }
      }
    })();

    return () => { mounted = false; };
  }, [question]);

  const handleApprove = async () => {
    setUpdating(true);
    try {
      await axios.post(`${API}/questions/${question.id}/approve`);
      toast.success("Question approved!");
      onUpdate();
    } catch (error) {
      toast.error("Failed to approve question");
    } finally {
      setUpdating(false);
    }
  };

  const handleReject = async () => {
    setUpdating(true);
    try {
      await axios.post(`${API}/questions/${question.id}/reject`);
      toast.success("Question marked for review");
      onUpdate();
    } catch (error) {
      toast.error("Failed to reject question");
    } finally {
      setUpdating(false);
    }
  };

  const handleDifficultyChange = async (difficulty) => {
    try {
      await axios.patch(`${API}/questions/${question.id}/difficulty?difficulty=${difficulty}`);
      toast.success("Difficulty updated");
      onUpdate();
    } catch (error) {
      toast.error("Failed to update difficulty");
    }
  };

  const handleTopicsChange = async (topics) => {
    try {
      await axios.patch(`${API}/questions/${question.id}/topics`, topics);
      toast.success("Topics updated");
      onUpdate();
    } catch (error) {
      toast.error("Failed to update topics");
    }
  };

  const handleSaveEdit = async () => {
    setUpdating(true);
    try {
      const updates = { text: editText };
      if (editMarks) updates.marks = parseInt(editMarks);
      if (editParts.length > 0) updates.parts = editParts;
      if (editSolution) updates.solution = editSolution;
      await axios.patch(`${API}/questions/${question.id}`, updates);
      toast.success("Question updated!");
      setEditMode(false);
      onUpdate();
    } catch (error) {
      toast.error("Failed to update");
    } finally {
      setUpdating(false);
    }
  };

  const handleReplaceImage = async (e, oldImageId) => {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    if (oldImageId) formData.append("old_image_id", oldImageId);
    try {
      await axios.post(`${API}/questions/${question.id}/replace-image`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      toast.success("Image replaced!");
      onUpdate();
    } catch (error) {
      toast.error("Failed to replace image");
    }
  };

  const handleRemoveImage = async (imageId) => {
    try {
      await axios.delete(`${API}/questions/${question.id}/images/${imageId}`);
      toast.success("Image removed!");
      onUpdate();
    } catch (error) {
      toast.error("Failed to remove image");
    }
  };

  if (!question) {
    return (
      <div className="h-full flex items-center justify-center text-slate-500">
        <div className="text-center">
          <Eye size={48} className="mx-auto mb-4" />
          <p className="text-sm">Select a question to view details</p>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="question-detail" className="h-full flex flex-col overflow-auto">
      {/* Header */}
      <div className="p-4 border-b border-black flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="font-sans text-xl font-bold">Q{question.question_number}</h2>
          {question.ge_id && (
            <span className="text-xs font-mono px-2 py-1 border-2 border-blue-800 bg-blue-50 text-blue-800 font-bold">{question.ge_id}</span>
          )}
          <StatusTag status={question.status} />
        </div>
        <div className="flex gap-2">
          <button
            data-testid="edit-question-btn"
            onClick={() => setEditMode(!editMode)}
            className={`px-3 py-2 border border-black text-xs ${editMode ? "bg-amber-50 border-amber-600" : ""}`}
          >
            {editMode ? "Cancel" : "Edit"}
          </button>
          <button
            data-testid="toggle-markscheme-btn"
            onClick={() => setShowMarkScheme(!showMarkScheme)}
            className={`px-3 py-2 border border-black text-xs flex items-center gap-1 ${showMarkScheme ? "bg-green-50" : ""}`}
          >
            <ListChecks size={14} />
            MS
          </button>
          <button
            data-testid="toggle-solution-btn"
            onClick={() => setShowSolution(!showSolution)}
            className={`px-3 py-2 border border-black text-xs flex items-center gap-1 ${showSolution ? "bg-purple-50" : ""}`}
          >
            <LightbulbFilament size={14} />
            Solution
          </button>
          <button
            data-testid="approve-question-btn"
            onClick={handleApprove}
            disabled={updating || question.status === "approved"}
            className="btn-primary flex items-center gap-1 text-sm py-2 px-3 disabled:opacity-50"
          >
            <Check size={14} weight="bold" />
          </button>
          <button
            data-testid="reject-question-btn"
            onClick={handleReject}
            disabled={updating}
            className="btn-secondary flex items-center gap-1 text-sm py-2 px-3"
          >
            <X size={14} weight="bold" />
          </button>
        </div>
      </div>
      
      {/* Content */}
      <div className="flex-1 p-4 overflow-auto">
        {/* Difficulty & Topics */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="text-xs tracking-widest uppercase font-bold block mb-2">Difficulty</label>
            <DifficultyBadge difficulty={question.difficulty} onChange={handleDifficultyChange} />
          </div>
          <div>
            <label className="text-xs tracking-widest uppercase font-bold block mb-2">Topics</label>
            <TopicTags 
              topics={question.topics} 
              allTopics={allTopics}
              onChange={handleTopicsChange}
            />
          </div>
        </div>

        {/* Question text */}
        <div className="mb-4">
          <label className="text-xs tracking-widest uppercase font-bold block mb-2">Question</label>
          {editMode ? (
            <textarea
              data-testid="edit-question-text"
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              className="w-full border border-black p-3 font-mono text-sm min-h-[100px]"
            />
          ) : (
            <div className="border border-black p-4 bg-slate-50">
              {renderLatex(question.text, question.latex)}
            </div>
          )}
        </div>

        {/* Marks - editable */}
        {editMode && (
          <div className="mb-4">
            <label className="text-xs tracking-widest uppercase font-bold block mb-2">Total Marks</label>
            <input
              data-testid="edit-marks-input"
              type="number"
              value={editMarks}
              onChange={(e) => setEditMarks(e.target.value)}
              className="border border-black p-2 w-24 text-sm"
            />
          </div>
        )}
        
        {/* Parts */}
        {question.parts?.length > 0 && (
          <div className="mb-4">
            <label className="text-xs tracking-widest uppercase font-bold block mb-2">Parts</label>
            <div className="border border-black">
              {(editMode ? editParts : question.parts).map((part, idx) => (
                <div key={idx} className="p-3 border-b border-black last:border-b-0">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-bold">({part.part_label})</span>
                    {part.ge_id && (
                      <span className="text-xs font-mono px-1 border border-blue-800 bg-blue-50 text-blue-800">{part.ge_id}</span>
                    )}
                    {editMode ? (
                      <input
                        type="number"
                        value={part.marks || ""}
                        onChange={(e) => {
                          const updated = [...editParts];
                          updated[idx] = { ...updated[idx], marks: parseInt(e.target.value) || null };
                          setEditParts(updated);
                        }}
                        className="border border-black px-2 py-0.5 w-16 text-xs"
                        placeholder="marks"
                      />
                    ) : (
                      part.marks && <span className="text-xs px-2 py-0.5 border border-black">{part.marks} marks</span>
                    )}
                  </div>
                  {editMode ? (
                    <textarea
                      value={part.text || ""}
                      onChange={(e) => {
                        const updated = [...editParts];
                        updated[idx] = { ...updated[idx], text: e.target.value };
                        setEditParts(updated);
                      }}
                      className="w-full border border-slate-300 p-2 text-sm font-mono min-h-[60px]"
                    />
                  ) : (
                    <div className="text-sm">{renderLatex(part.text, part.latex)}</div>
                  )}
                  {part.mark_scheme && !editMode && (
                    <div className="mt-2 p-2 bg-green-50 border-l-2 border-green-600 text-xs">
                      <strong>Mark Scheme:</strong> {renderLatex(part.mark_scheme, part.mark_scheme_latex)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Save button in edit mode */}
        {editMode && (
          <button
            data-testid="save-edit-btn"
            onClick={handleSaveEdit}
            disabled={updating}
            className="btn-primary w-full mb-4 disabled:opacity-50"
          >
            {updating ? "Saving..." : "Save Changes"}
          </button>
        )}
        
        {/* Images/Diagrams with replace/remove */}
        <div className="mb-4">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs tracking-widest uppercase font-bold">
              Diagrams ({images.length})
            </label>
            <label className="text-xs px-2 py-1 border border-dashed border-black cursor-pointer hover:bg-slate-100">
              <Plus size={10} className="inline mr-1" /> Add Image
              <input
                data-testid="add-image-input"
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => handleReplaceImage(e, null)}
              />
            </label>
          </div>
          {images.length > 0 ? (
            <div className="grid grid-cols-2 gap-3">
              {images.map((img) => (
                <div
                  key={img.id}
                  data-testid={`diagram-${img.id}`}
                  className="border border-black p-2 relative group"
                >
                  <div className="absolute -top-2 left-2 bg-white px-1 text-xs font-mono">
                    Fig {img.page_number}
                  </div>
                  <img
                    src={`${API}/images/${img.id}/download`}
                    alt={img.description || "Diagram"}
                    className="w-full h-auto"
                  />
                  {/* Image action buttons */}
                  <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <label className="p-1 bg-white border border-black cursor-pointer hover:bg-blue-50 text-xs">
                      Replace
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(e) => handleReplaceImage(e, img.id)}
                      />
                    </label>
                    <button
                      onClick={() => handleRemoveImage(img.id)}
                      className="p-1 bg-white border border-red-500 text-red-600 hover:bg-red-50 text-xs"
                    >
                      <X size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="border border-dashed border-slate-400 p-4 text-center text-slate-500 text-xs">
              No diagrams
            </div>
          )}
        </div>

        {/* Mark Scheme Panel */}
        {showMarkScheme && (
          <div className="mb-4">
            <MarkSchemePanel question={question} entries={markSchemeEntries} />
          </div>
        )}

        {/* Solution Panel */}
        {showSolution && (
          <div className="mb-4 border border-purple-300 p-4 bg-purple-50">
            <label className="text-xs tracking-widest uppercase font-bold block mb-3">Solution</label>
            {editMode ? (
              <textarea
                value={editSolution || question.solution || ""}
                onChange={(e) => setEditSolution(e.target.value)}
                placeholder="Solution (optional)"
                className="w-full border border-black p-2 font-mono text-xs min-h-32"
              />
            ) : question.solution ? (
              <div className="prose prose-sm max-w-none">
                {renderLatex(question.solution, question.solution_latex)}
              </div>
            ) : (
              <p className="text-slate-500 text-xs italic">No solution yet. Click "Solutions" button to generate.</p>
            )}
          </div>
        )}

        {/* Metadata */}
        <div className="grid grid-cols-3 gap-3">
          <div className="border border-black p-3">
            <label className="text-xs tracking-widest uppercase font-bold block mb-1">Marks</label>
            <p className="text-lg font-bold">{question.marks || "—"}</p>
          </div>
          <div className="border border-black p-3">
            <label className="text-xs tracking-widest uppercase font-bold block mb-1">Confidence</label>
            <p className="text-lg font-bold">{(question.confidence * 100).toFixed(0)}%</p>
          </div>
          <div className="border border-black p-3">
            <label className="text-xs tracking-widest uppercase font-bold block mb-1">Parts</label>
            <p className="text-lg font-bold">{question.parts?.length || 0}</p>
          </div>
        </div>
      </div>
    </div>
  );
};

// ============ Papers List ============
const PapersList = ({ papers, selectedId, onSelect, onDelete }) => {
  const formatDate = (isoStr) => {
    if (!isoStr) return "";
    const d = new Date(isoStr);
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' }) + ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="border-b border-black">
      <div className="p-3 border-b border-black">
        <label className="text-xs tracking-widest uppercase font-bold">Papers</label>
      </div>
      <div className="max-h-48 overflow-auto">
        {papers.length === 0 ? (
          <div className="p-3 text-center text-slate-500 text-xs">
            No papers yet
          </div>
        ) : (
          papers.map((paper) => (
            <div
              key={paper.id}
              data-testid={`paper-row-${paper.id}`}
              className={`p-2 border-b border-slate-200 text-sm ${
                selectedId === paper.id ? "bg-slate-100" : "hover:bg-slate-50"
              }`}
            >
              <div className="flex items-center justify-between cursor-pointer" onClick={() => onSelect(paper)}>
                <div>
                  <span className="font-semibold">{paper.board}</span>
                  <span className="text-slate-500 ml-1 text-xs">
                    {paper.exam_year} P{paper.paper_number}
                  </span>
                  {paper.ge_code && (
                    <span className="ml-2 text-xs font-mono px-1 border border-blue-800 bg-blue-50 text-blue-800">{paper.ge_code}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <StatusTag status={paper.status} />
                  <button
                    data-testid={`delete-paper-${paper.id}`}
                    onClick={(e) => { e.stopPropagation(); onDelete(paper.id); }}
                    className="p-1 text-red-500 hover:bg-red-50 border border-transparent hover:border-red-300"
                    title="Delete paper"
                  >
                    <X size={12} weight="bold" />
                  </button>
                </div>
              </div>
              <div className="text-xs text-slate-400 mt-1">{formatDate(paper.created_at)}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

// ============ Stats Card ============
const StatsCard = ({ stats }) => {
  if (!stats) return null;
  
  return (
    <div className="p-3 border-b border-black bg-slate-50">
      <div className="grid grid-cols-5 gap-2 text-center">
        <div>
          <p className="text-xl font-bold">{stats.total_papers}</p>
          <p className="text-xs text-slate-500">Papers</p>
        </div>
        <div>
          <p className="text-xl font-bold">{stats.total_questions}</p>
          <p className="text-xs text-slate-500">Questions</p>
        </div>
        <div>
          <p className="text-xl font-bold text-green-600">{stats.approved_questions}</p>
          <p className="text-xs text-slate-500">Approved</p>
        </div>
        <div>
          <p className="text-xl font-bold text-amber-600">{stats.pending_review}</p>
          <p className="text-xs text-slate-500">Review</p>
        </div>
        <div>
          <p className="text-xl font-bold text-blue-600">{stats.total_mark_schemes || 0}</p>
          <p className="text-xs text-slate-500">Schemes</p>
        </div>
      </div>
    </div>
  );
};

// ============ Main Dashboard ============
const Dashboard = () => {
  const [papers, setPapers] = useState([]);
  const [selectedPaper, setSelectedPaper] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [selectedQuestionId, setSelectedQuestionId] = useState(null);
  const [extractionJobId, setExtractionJobId] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [allTopics, setAllTopics] = useState({});
  const [updating, setUpdating] = useState(false);
  const [showFullPreview, setShowFullPreview] = useState(false);

  // Get selected question object from questions array by ID
  const selectedQuestion = questions.find(q => q.id === selectedQuestionId) || null;

  const fetchData = useCallback(async () => {
    try {
      const [papersRes, statsRes, topicsRes] = await Promise.all([
        axios.get(`${API}/papers`),
        axios.get(`${API}/stats`),
        axios.get(`${API}/topics/categories`)
      ]);
      setPapers(papersRes.data);
      setStats(statsRes.data);
      setAllTopics(topicsRes.data);
    } catch (error) {
      console.error("Failed to fetch data:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchQuestions = useCallback(async (paperId) => {
    try {
      const response = await axios.get(`${API}/questions?paper_id=${paperId}`);
      setQuestions(response.data);
    } catch (error) {
      console.error("Failed to fetch questions:", error);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (selectedPaper) {
      fetchQuestions(selectedPaper.id);
    }
  }, [selectedPaper, fetchQuestions]);

  const handlePaperCreated = (paper) => {
    setPapers([...papers, paper]);
    setSelectedPaper(paper);
  };

  const handlePaperSelect = (paper) => {
    setSelectedPaper(paper);
    setSelectedQuestionId(null);
    setQuestions([]);
  };

  const handleDeletePaper = async (paperId) => {
    if (!window.confirm("Delete this paper and all its questions?")) return;
    try {
      await axios.delete(`${API}/papers/${paperId}`);
      toast.success("Paper deleted");
      if (selectedPaper?.id === paperId) {
        setSelectedPaper(null);
        setSelectedQuestionId(null);
        setQuestions([]);
      }
      fetchData();
    } catch (error) {
      toast.error("Failed to delete paper");
    }
  };

  const handleUploadComplete = (jobId) => {
    setExtractionJobId(jobId);
  };

  const handleExtractionComplete = () => {
    setExtractionJobId(null);
    if (selectedPaper) {
      fetchQuestions(selectedPaper.id);
    }
    fetchData();
  };

  const handleQuestionUpdate = () => {
    if (selectedPaper) {
      fetchQuestions(selectedPaper.id);
    }
    fetchData();
  };

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center">
          <ArrowClockwise size={48} className="animate-spin mx-auto mb-4" />
          <p className="text-sm">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" data-testid="dashboard">
      {/* Header */}
      <header className="border-b border-black">
        <div className="p-4 flex items-center justify-between">
          <div>
            <h1 className="font-sans text-2xl font-bold tracking-tight">GCSE Question Bank</h1>
            <p className="text-xs text-slate-600 mt-1">Extract • Review • Organise</p>
          </div>
          <button
            data-testid="refresh-btn"
            onClick={fetchData}
            className="p-2 border border-black hover:bg-black hover:text-white transition-colors"
          >
            <ArrowClockwise size={18} />
          </button>
        </div>
        <StatsCard stats={stats} />
      </header>

      {/* Main content - dual pane */}
      <div className="dual-pane" style={{ height: "calc(100vh - 140px)" }}>
        {/* Left pane - Papers & Questions */}
        <div className="border-r border-black flex flex-col overflow-hidden">
          {/* Collapsible paper form */}
          {!selectedPaper ? (
            <>
              <PaperForm onPaperCreated={handlePaperCreated} />
              <PapersList 
                papers={papers} 
                selectedId={selectedPaper?.id} 
                onSelect={handlePaperSelect}
                onDelete={handleDeletePaper}
              />
            </>
          ) : (
            <>
              {/* Selected paper header */}
              <div className="p-3 border-b border-black flex flex-wrap items-center gap-2 bg-slate-50">
                <div className="flex items-center gap-2">
                  <span className="font-sans font-bold">{selectedPaper.board}</span>
                  <span className="text-sm text-slate-500">{selectedPaper.exam_year} P{selectedPaper.paper_number} {selectedPaper.tier}</span>
                  {selectedPaper.ge_code && (
                    <span className="text-xs font-mono px-2 py-0.5 border-2 border-blue-800 bg-blue-50 text-blue-800 font-bold">{selectedPaper.ge_code}</span>
                  )}
                  <StatusTag status={selectedPaper.status} />
                </div>
                <div className="flex flex-wrap gap-2">
                  {selectedPaper.status === "extracted" && (
                    <button
                      data-testid="re-extract-btn"
                      onClick={async () => {
                        try {
                          const res = await axios.post(`${API}/papers/${selectedPaper.id}/re-extract`);
                          toast.success("Re-extraction started with improved cropping!");
                          setExtractionJobId(res.data.job_id);
                        } catch (error) {
                          toast.error("Failed: " + (error.response?.data?.detail || error.message));
                        }
                      }}
                      className="text-xs px-2 py-1 border border-amber-600 text-amber-700 hover:bg-amber-50"
                    >
                      Re-Extract
                    </button>
                  )}
                  {selectedPaper.status === "extracted" && (
                    <button
                      data-testid="classify-btn"
                      onClick={async () => {
                        try {
                          setUpdating(true);
                          const res = await axios.post(`${API}/papers/${selectedPaper.id}/classify`);
                          toast.success(`Classified ${res.data.classified}/${res.data.total} questions`);
                          // Reload questions
                          const q = await axios.get(`${API}/questions?paper_id=${selectedPaper.id}`);
                          setQuestions(q.data);
                        } catch (error) {
                          toast.error("Classification failed: " + (error.response?.data?.detail || error.message));
                        } finally {
                          setUpdating(false);
                        }
                      }}
                      disabled={updating}
                      className="text-xs px-2 py-1 border border-blue-600 text-blue-700 hover:bg-blue-50 disabled:opacity-50"
                    >
                      Classify
                    </button>
                  )}
                  {selectedPaper.status === "extracted" && (
                    <button
                      data-testid="solutions-btn"
                      onClick={async () => {
                        try {
                          setUpdating(true);
                          const res = await axios.post(`${API}/papers/${selectedPaper.id}/generate-solutions`);
                          toast.success(`Generated ${res.data.generated}/${res.data.total} solutions`);
                          // Reload questions
                          const q = await axios.get(`${API}/questions?paper_id=${selectedPaper.id}`);
                          setQuestions(q.data);
                        } catch (error) {
                          toast.error("Solution generation failed: " + (error.response?.data?.detail || error.message));
                        } finally {
                          setUpdating(false);
                        }
                      }}
                      disabled={updating}
                      className="text-xs px-2 py-1 border border-purple-600 text-purple-700 hover:bg-purple-50 disabled:opacity-50"
                    >
                      Solutions
                    </button>
                  )}
                  {selectedPaper.status === "extracted" && (
                    <button
                      data-testid="view-all-btn"
                      onClick={() => setShowFullPreview(true)}
                      className="text-xs px-2 py-1 border border-slate-600 text-slate-700 hover:bg-slate-50"
                    >
                      View All
                    </button>
                  )}
                  <button
                    data-testid="back-to-papers-btn"
                    onClick={() => { setSelectedPaper(null); setSelectedQuestionId(null); setQuestions([]); }}
                    className="text-xs px-2 py-1 border border-black hover:bg-black hover:text-white"
                  >
                    All Papers
                  </button>
                </div>
              </div>
              
              {/* Upload zones - compact inline */}
              <div className="grid grid-cols-2 border-b border-black">
                <PDFUploadZone 
                  paperId={selectedPaper.id} 
                  onUploadComplete={handleUploadComplete}
                  type="paper"
                />
                <PDFUploadZone 
                  paperId={selectedPaper.id} 
                  onUploadComplete={() => {
                    toast.success("Mark scheme processing...");
                    setTimeout(() => fetchQuestions(selectedPaper.id), 5000);
                  }}
                  type="markscheme"
                />
              </div>
              
              {extractionJobId && (
                <ExtractionStatus 
                  jobId={extractionJobId} 
                  onComplete={handleExtractionComplete}
                />
              )}
              
              {/* Question list - takes all remaining space */}
              <div className="flex-1 overflow-hidden">
                <QuestionList
                  questions={questions}
                  selectedId={selectedQuestionId}
                  onSelect={(q) => setSelectedQuestionId(q.id)}
                />
              </div>
            </>
          )}
        </div>

        {/* Right pane - Question Detail */}
        <div className="overflow-hidden">
          <QuestionDetail
            question={selectedQuestion}
            onUpdate={handleQuestionUpdate}
            allTopics={allTopics}
          />
        </div>
      </div>

      {/* Full Preview Modal */}
      {showFullPreview && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded border-2 border-black max-w-4xl max-h-[90vh] overflow-auto w-full">
            <div className="sticky top-0 bg-white border-b border-black p-4 flex items-center justify-between">
              <h2 className="text-xl font-bold">All Questions - {selectedPaper?.board} P{selectedPaper?.paper_number}</h2>
              <button
                onClick={() => setShowFullPreview(false)}
                className="text-2xl font-bold hover:bg-slate-100 px-3 py-1"
              >
                ✕
              </button>
            </div>
            <div className="p-4">
              {questions.map((q) => (
                <div key={q.id} className="mb-6 pb-6 border-b border-slate-300 last:border-b-0">
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="font-bold text-lg">Q{q.question_number}</h3>
                    <div className="flex gap-2">
                      {q.marks && <span className="text-xs px-2 py-1 bg-slate-100 border border-slate-300">Marks: {q.marks}</span>}
                      <StatusTag status={q.status} />
                    </div>
                  </div>
                  <div className="text-sm whitespace-pre-wrap mb-2">{renderLatex(q.text, q.latex)}</div>
                  {q.parts && q.parts.length > 0 && (
                    <div className="ml-4 mt-2 text-xs">
                      <strong>Parts:</strong> {q.parts.map((p, i) => `(${p.part_label}) ${p.marks ? p.marks + 'mk' : ''}`).join(', ')}
                    </div>
                  )}
                  {q.topics && q.topics.length > 0 && (
                    <div className="mt-2">
                      {q.topics.map((t) => (
                        <span key={t} className="inline-block text-xs px-2 py-1 border border-slate-400 bg-slate-50 mr-1 mb-1">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ============ App Router ============
function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="bottom-right" />
    </div>
  );
}

export default App;
