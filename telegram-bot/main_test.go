package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestPollingBatchFitsResponseLimit(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	api := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		var request struct {
			Limit int `json:"limit"`
		}
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			t.Error(err)
		}
		if request.Limit != 10 {
			t.Errorf("слишком большая пачка: %d, ожидается 10", request.Limit)
		}
		io.WriteString(w, `{"ok":true,"result":[]}`)
		cancel()
	})
	b := &bot{api: api, active: make(map[int64]bool)}
	b.run(ctx)
}

func testClient(t *testing.T, h http.HandlerFunc) *telegram {
	t.Helper()
	server := httptest.NewServer(h)
	t.Cleanup(server.Close)
	return &telegram{token: "secret", base: server.URL, client: server.Client()}
}

func TestDownloadLimitsAndPath(t *testing.T) {
	for _, tc := range []struct {
		name, path string
		size       int
		wantErr    bool
	}{
		{"обычный", "documents/file.cpp", 4, false},
		{"граница", "documents/file.cpp", maxInput, false},
		{"слишком большой", "documents/file.cpp", maxInput + 1, true},
		{"обход", "../secret", 1, true},
		{"абсолютный", "https://evil.test/a", 1, true},
		{"кодирование", "documents/%2e%2e/file", 1, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			api := testClient(t, func(w http.ResponseWriter, r *http.Request) {
				if strings.HasSuffix(r.URL.Path, "getFile") {
					json.NewEncoder(w).Encode(map[string]any{"ok": true, "result": map[string]any{"file_path": tc.path}})
					return
				}
				io.Copy(w, io.LimitReader(repeatReader{}, int64(tc.size)))
			})
			err := api.download(context.Background(), "id", filepath.Join(t.TempDir(), "input.cpp"))
			if (err != nil) != tc.wantErr {
				t.Fatalf("ошибка: %v", err)
			}
		})
	}
}

type repeatReader struct{}

func (repeatReader) Read(p []byte) (int, error) {
	for i := range p {
		p[i] = 'x'
	}
	return len(p), nil
}

func TestAPIRejectsErrorsAndLargeResponses(t *testing.T) {
	for _, body := range []string{`{"ok":false,"description":"secret"}`, strings.Repeat("x", maxAPIResponse+1), `{"ok":true} мусор`} {
		api := testClient(t, func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, body) })
		err := api.call(context.Background(), "getFile", map[string]string{}, nil)
		if err == nil || strings.Contains(err.Error(), "secret") {
			t.Fatalf("небезопасная ошибка: %v", err)
		}
	}
}

func TestSendDocument(t *testing.T) {
	filename := filepath.Join(t.TempDir(), "result.png")
	if err := os.WriteFile(filename, []byte("png-data"), 0600); err != nil {
		t.Fatal(err)
	}
	api := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "sendDocument") {
			t.Error(r.URL.Path)
		}
		if err := r.ParseMultipartForm(1 << 20); err != nil {
			t.Error(err)
			return
		}
		if r.FormValue("chat_id") != "42" {
			t.Error("неверный чат")
		}
		f, h, err := r.FormFile("document")
		if err != nil {
			t.Error(err)
			return
		}
		defer f.Close()
		data, _ := io.ReadAll(f)
		if h.Filename != "result.png" || string(data) != "png-data" {
			t.Error("неверный документ")
		}
		io.WriteString(w, `{"ok":true,"result":{}}`)
	})
	if err := api.sendDocument(context.Background(), 42, filename); err != nil {
		t.Fatal(err)
	}
}

func TestRunRenderer(t *testing.T) {
	dir := t.TempDir()
	executable := filepath.Join(dir, "renderer")
	script := "#!/bin/sh\n[ -z \"$TELEGRAM_BOT_TOKEN\" ] || exit 9\n[ \"$1\" = \"input.cpp\" ] || exit 10\n[ \"$2\" = \"--out\" ] || exit 11\n" + rendererCacheScript + "mkdir -p \"$3\"\nprintf 'png' > \"$3/result.png\"\nprintf '%s\\n' \"$@\" > arguments\n"
	if err := os.WriteFile(executable, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TELEGRAM_BOT_TOKEN", "secret")
	t.Setenv("HOME", t.TempDir())
	t.Setenv("XDG_CACHE_HOME", t.TempDir())
	t.Setenv("PYTHONDONTWRITEBYTECODE", "0")
	originalHome := os.Getenv("HOME")
	originalTemp := os.Getenv("TMPDIR")
	originalCache := os.Getenv("XDG_CACHE_HOME")
	paths, err := render(context.Background(), executable, dir)
	if err != nil || len(paths) != 1 {
		t.Fatalf("результат: %v, %v", paths, err)
	}
	args, _ := os.ReadFile(filepath.Join(dir, "arguments"))
	for _, flag := range []string{"--no-ui", "--no-html", "hexagon", "study", "hide", "symbols", "--page-height\n0", "--png\n2"} {
		if !bytes.Contains(args, []byte(flag)) {
			t.Errorf("нет %s", flag)
		}
	}
	for _, path := range []string{"temporary-data", "home-data", "cache/font-data"} {
		if _, err := os.Stat(filepath.Join(dir, path)); err != nil {
			t.Fatalf("дочерний процесс не создал локальный файл %s: %v", path, err)
		}
	}
	if os.Getenv("HOME") != originalHome || os.Getenv("TMPDIR") != originalTemp || os.Getenv("XDG_CACHE_HOME") != originalCache || os.Getenv("PYTHONDONTWRITEBYTECODE") != "0" {
		t.Fatal("окружение бота изменилось вместе с окружением обработчика")
	}
}

// Проверки перед записью защищают окружение тестов при регрессии изоляции.
const rendererCacheScript = `[ "$TMPDIR" = "$PWD" ] || exit 14
[ "$HOME" = "$PWD" ] || exit 15
[ "$XDG_CACHE_HOME" = "$PWD/cache" ] || exit 16
[ "$PYTHONDONTWRITEBYTECODE" = 1 ] || exit 17
printf temporary > "$TMPDIR/temporary-data"
printf home > "$HOME/home-data"
mkdir -p "$XDG_CACHE_HOME"
printf cache > "$XDG_CACHE_HOME/font-data"
`

func TestRendererTimeout(t *testing.T) {
	dir := t.TempDir()
	executable := filepath.Join(dir, "renderer")
	if err := os.WriteFile(executable, []byte("#!/bin/sh\nsleep 30 &\nwait\n"), 0700); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	start := time.Now()
	_, err := render(ctx, executable, dir)
	if err == nil || time.Since(start) > 3*time.Second {
		t.Fatalf("таймаут не сработал: %v", err)
	}
}

func TestOutputLimits(t *testing.T) {
	for _, count := range []int{0, 1, maxOutputs + 1} {
		dir := t.TempDir()
		for i := 0; i < count; i++ {
			if err := os.WriteFile(filepath.Join(dir, strings.Repeat("x", i+1)+".png"), []byte("png"), 0600); err != nil {
				t.Fatal(err)
			}
		}
		paths, err := outputFiles(dir)
		if (err != nil) != (count == 0 || count > maxOutputs) {
			t.Fatalf("%d: %v %v", count, paths, err)
		}
	}
	dir := t.TempDir()
	f, err := os.Create(filepath.Join(dir, "large.png"))
	if err != nil {
		t.Fatal(err)
	}
	f.Truncate(maxOutputBytes + 1)
	f.Close()
	if _, err := outputFiles(dir); err == nil {
		t.Fatal("не проверен размер")
	}
}

func TestAdmission(t *testing.T) {
	b := &bot{active: make(map[int64]bool)}
	if !b.acquire(1) || b.acquire(1) || !b.acquire(2) || b.acquire(3) {
		t.Fatal("не соблюдены лимиты")
	}
	b.release(1)
	if !b.acquire(3) {
		t.Fatal("слот не освобождён")
	}
}

func TestMetadataLimit(t *testing.T) {
	var downloaded bool
	api := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "getFile") {
			json.NewEncoder(w).Encode(map[string]any{"ok": true, "result": map[string]any{"file_path": "documents/file.cpp", "file_size": maxInput + 1}})
			return
		}
		downloaded = true
	})
	if err := api.download(context.Background(), "id", filepath.Join(t.TempDir(), "input.cpp")); err == nil || downloaded {
		t.Fatal("метаданные не ограничены")
	}
}

func TestProcessDocument(t *testing.T) {
	var sent int
	api := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasSuffix(r.URL.Path, "getFile"):
			io.WriteString(w, `{"ok":true,"result":{"file_path":"documents/source.cpp","file_size":12}}`)
		case strings.Contains(r.URL.Path, "/file/"):
			io.WriteString(w, "int main(){}")
		case strings.HasSuffix(r.URL.Path, "sendDocument"):
			if err := r.ParseMultipartForm(1 << 20); err != nil {
				t.Error(err)
				return
			}
			file, _, err := r.FormFile("document")
			if err != nil {
				t.Error(err)
				return
			}
			data, _ := io.ReadAll(file)
			file.Close()
			if string(data) != "png" {
				t.Error("результат повреждён")
			}
			sent++
			io.WriteString(w, `{"ok":true,"result":{}}`)
		default:
			t.Error("неожиданный запрос")
		}
	})
	dir := t.TempDir()
	executable := filepath.Join(dir, "renderer")
	script := "#!/bin/sh\n[ \"$(cat input.cpp)\" = 'int main(){}' ] || exit 12\nmkdir -p \"$3\"\nprintf png > \"$3/first.png\"\nprintf png > \"$3/second.png\"\n"
	if err := os.WriteFile(executable, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	b := &bot{api: api, executable: executable}
	if err := b.process(context.Background(), 42, "id"); err != nil {
		t.Fatal(err)
	}
	if sent != 2 {
		t.Fatalf("отправлено %d PNG", sent)
	}
}

func TestProcessCleansTemporaryFiles(t *testing.T) {
	for _, tc := range []struct {
		name, stage, wantError string
	}{
		{"успех", "success", ""},
		{"неполное скачивание", "download", "исходный файл превышает"},
		{"ошибка построения", "render", "не удалось построить схему"},
		{"таймаут построения", "timeout", "обработка отменена"},
		{"отмена построения", "cancel", "обработка отменена"},
		{"ошибка отправки", "upload", "Telegram отклонил запрос"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			parent := t.TempDir()
			t.Setenv("TMPDIR", parent)
			executable := filepath.Join(t.TempDir(), "renderer")
			script := "#!/bin/sh\n" + rendererCacheScript + "mkdir -p \"$3\"\nprintf png > \"$3/result.png\"\n"
			switch tc.stage {
			case "render":
				script += "exit 13\n"
			case "timeout", "cancel":
				script += "sleep 30 &\nwait\n"
			}
			if err := os.WriteFile(executable, []byte(script), 0700); err != nil {
				t.Fatal(err)
			}
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			if tc.stage == "timeout" {
				var timeoutCancel context.CancelFunc
				ctx, timeoutCancel = context.WithTimeout(ctx, time.Second)
				defer timeoutCancel()
			}
			api := testClient(t, func(w http.ResponseWriter, r *http.Request) {
				switch {
				case strings.HasSuffix(r.URL.Path, "getFile"):
					io.WriteString(w, `{"ok":true,"result":{"file_path":"documents/source.cpp","file_size":12}}`)
				case strings.Contains(r.URL.Path, "/file/"):
					if tc.stage == "download" {
						io.Copy(w, io.LimitReader(repeatReader{}, maxInput+1))
					} else {
						io.WriteString(w, "int main(){}")
					}
				case strings.HasSuffix(r.URL.Path, "sendDocument"):
					io.Copy(io.Discard, r.Body)
					if tc.stage == "upload" {
						io.WriteString(w, `{"ok":false,"error_code":429}`)
					} else {
						io.WriteString(w, `{"ok":true,"result":{}}`)
					}
				default:
					t.Error("неожиданный запрос")
				}
			})
			b := &bot{api: api, executable: executable}
			finished := make(chan error, 1)
			go func() { finished <- b.process(ctx, 42, "id") }()
			if tc.stage == "cancel" {
				// Отмена после появления PNG проверяет удаление и исходника, и результата.
				deadline := time.NewTimer(3 * time.Second)
				defer deadline.Stop()
				ticker := time.NewTicker(10 * time.Millisecond)
				defer ticker.Stop()
			waitForOutput:
				for {
					select {
					case <-deadline.C:
						cancel()
						<-finished
						t.Fatal("обработчик не создал PNG до отмены")
					case <-ticker.C:
						files, err := filepath.Glob(filepath.Join(parent, "blockwright-telegram-*", "output", "result.png"))
						if err != nil {
							t.Fatal(err)
						}
						if len(files) != 0 {
							cancel()
							break waitForOutput
						}
					}
				}
			}
			select {
			case err := <-finished:
				if tc.wantError == "" && err != nil || tc.wantError != "" && (err == nil || !strings.Contains(err.Error(), tc.wantError)) {
					t.Fatalf("неожиданный результат обработки: %v", err)
				}
			case <-time.After(5 * time.Second):
				cancel()
				<-finished
				t.Fatal("обработка не завершилась вовремя")
			}
			entries, err := os.ReadDir(parent)
			if err != nil || len(entries) != 0 {
				t.Fatalf("временные данные остались после обработки: %v, %v", entries, err)
			}
		})
	}
}

func TestProcessReportsCleanupFailureSafely(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root обходит права каталогов")
	}
	parent := t.TempDir()
	t.Setenv("TMPDIR", parent)
	// Возвращаем права до штатной очистки t.TempDir даже при падении проверки.
	t.Cleanup(func() {
		outputs, err := filepath.Glob(filepath.Join(parent, "blockwright-telegram-*", "output"))
		if err != nil {
			t.Error(err)
		}
		for _, output := range outputs {
			if err := os.Chmod(output, 0700); err != nil {
				t.Error(err)
			}
		}
	})
	executable := filepath.Join(t.TempDir(), "renderer")
	script := "#!/bin/sh\nmkdir -p \"$3\"\nprintf png > \"$3/result.png\"\nchmod 500 \"$3\"\n"
	if err := os.WriteFile(executable, []byte(script), 0700); err != nil {
		t.Fatal(err)
	}
	api := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasSuffix(r.URL.Path, "getFile"):
			io.WriteString(w, `{"ok":true,"result":{"file_path":"documents/source.cpp","file_size":12}}`)
		case strings.Contains(r.URL.Path, "/file/"):
			io.WriteString(w, "int main(){}")
		default:
			io.Copy(io.Discard, r.Body)
			io.WriteString(w, `{"ok":true,"result":{}}`)
		}
	})
	var logs bytes.Buffer
	previousOutput := log.Writer()
	log.SetOutput(&logs)
	t.Cleanup(func() { log.SetOutput(previousOutput) })
	b := &bot{api: api, executable: executable}
	err := b.process(context.Background(), 42, "id")
	if err == nil {
		t.Fatal("ошибка удаления временных файлов проигнорирована")
	}
	if logs.Len() == 0 {
		t.Fatal("ошибка удаления временных файлов не записана в журнал")
	}
	for _, sensitive := range []string{parent, "blockwright-telegram-", api.token, "source.cpp", "input.cpp"} {
		if strings.Contains(logs.String(), sensitive) || strings.Contains(err.Error(), sensitive) {
			t.Fatal("ошибка очистки раскрывает локальный путь или данные запроса")
		}
	}
}

func TestSendDocumentRejectsAPIError(t *testing.T) {
	path := filepath.Join(t.TempDir(), "result.png")
	if err := os.WriteFile(path, []byte("png"), 0600); err != nil {
		t.Fatal(err)
	}
	api := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		io.Copy(io.Discard, r.Body)
		io.WriteString(w, `{"ok":false,"error_code":429,"description":"secret"}`)
	})
	if err := api.sendDocument(context.Background(), 42, path); err == nil || strings.Contains(err.Error(), "secret") {
		t.Fatalf("ошибка: %v", err)
	}
}

func TestOutputRejectsSymlink(t *testing.T) {
	dir := t.TempDir()
	if err := os.Symlink("/etc/passwd", filepath.Join(dir, "result.png")); err != nil {
		t.Fatal(err)
	}
	if _, err := outputFiles(dir); err == nil {
		t.Fatal("принят symlink")
	}
}

func TestHandleRejectsDocumentBeforeDownload(t *testing.T) {
	for _, doc := range []document{{FileName: "source.exe", FileID: "id"}, {FileName: "source.cpp", FileID: "id", FileSize: maxInput + 1}} {
		requests := 0
		api := testClient(t, func(w http.ResponseWriter, r *http.Request) {
			requests++
			if !strings.HasSuffix(r.URL.Path, "sendMessage") {
				t.Error("неожиданный запрос")
			}
			io.WriteString(w, `{"ok":true,"result":{}}`)
		})
		b := &bot{api: api, active: make(map[int64]bool)}
		m := &message{Document: &doc}
		m.Chat.ID = 42
		b.handle(context.Background(), m)
		if requests != 1 || len(b.active) != 0 {
			t.Fatal("неверный отказ")
		}
	}
}
