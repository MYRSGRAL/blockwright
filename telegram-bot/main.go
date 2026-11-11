package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

const (
	maxInput          = 256 * 1024
	maxAPIResponse    = 1 << 20
	maxOutputs        = 10
	maxOutputBytes    = 20 << 20
	processingTimeout = 90 * time.Second
	instruction       = "Пришлите документ .cpp, .cc или .cxx размером до 256 КиБ. Я построю блок-схему и верну PNG как документы без сжатия. Код не исполняется. Одновременно доступны две обработки, по одной на пользователя."
)

var safeFilePath = regexp.MustCompile(`^[A-Za-z0-9_-]+(/[A-Za-z0-9_.-]+)+$`)
var safeToken = regexp.MustCompile(`^[0-9]+:[A-Za-z0-9_-]+$`)

type telegram struct {
	token, base string
	client      *http.Client
}
type document struct {
	FileID   string `json:"file_id"`
	FileName string `json:"file_name"`
	FileSize int64  `json:"file_size"`
}
type message struct {
	Chat struct {
		ID int64 `json:"id"`
	} `json:"chat"`
	From *struct {
		ID int64 `json:"id"`
	} `json:"from"`
	Text     string    `json:"text"`
	Document *document `json:"document"`
}
type update struct {
	ID      int64    `json:"update_id"`
	Message *message `json:"message"`
}

func (t *telegram) endpoint(method string) string { return t.base + "/bot" + t.token + "/" + method }

func (t *telegram) response(resp *http.Response, result any) error {
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("Telegram HTTP: %d", resp.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, maxAPIResponse+1))
	if err != nil {
		return errors.New("не удалось прочитать ответ Telegram")
	}
	if len(data) > maxAPIResponse {
		return errors.New("ответ Telegram превышает лимит")
	}
	var envelope struct {
		OK     bool            `json:"ok"`
		Result json.RawMessage `json:"result"`
		Code   int             `json:"error_code"`
	}
	if json.Unmarshal(data, &envelope) != nil {
		return errors.New("некорректный JSON Telegram")
	}
	if !envelope.OK {
		return fmt.Errorf("Telegram отклонил запрос (код %d)", envelope.Code)
	}
	if result != nil && json.Unmarshal(envelope.Result, result) != nil {
		return errors.New("некорректный результат Telegram")
	}
	return nil
}

func (t *telegram) call(ctx context.Context, method string, payload any, result any) error {
	data, err := json.Marshal(payload)
	if err != nil {
		return errors.New("не удалось подготовить запрос Telegram")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, t.endpoint(method), bytes.NewReader(data))
	if err != nil {
		return errors.New("не удалось создать запрос Telegram")
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := t.client.Do(req)
	if err != nil {
		return errors.New("ошибка соединения с Telegram")
	}
	return t.response(resp, result)
}

func (t *telegram) sendText(ctx context.Context, chat int64, text string) error {
	return t.call(ctx, "sendMessage", map[string]any{"chat_id": chat, "text": text}, nil)
}

func validFilePath(path string) bool {
	if !safeFilePath.MatchString(path) || len(path) > 1024 {
		return false
	}
	for _, part := range strings.Split(path, "/") {
		if part == "." || part == ".." {
			return false
		}
	}
	return true
}

func (t *telegram) download(ctx context.Context, id, destination string) error {
	var file struct {
		Path string `json:"file_path"`
		Size int64  `json:"file_size"`
	}
	if err := t.call(ctx, "getFile", map[string]string{"file_id": id}, &file); err != nil {
		return err
	}
	if file.Size < 0 || file.Size > maxInput {
		return errors.New("исходный файл превышает 256 КиБ")
	}
	if !validFilePath(file.Path) {
		return errors.New("Telegram вернул недопустимый путь файла")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, t.base+"/file/bot"+t.token+"/"+file.Path, nil)
	if err != nil {
		return errors.New("не удалось подготовить скачивание")
	}
	resp, err := t.client.Do(req)
	if err != nil {
		return errors.New("ошибка скачивания из Telegram")
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return errors.New("Telegram отклонил скачивание")
	}
	if resp.ContentLength > maxInput {
		return errors.New("исходный файл превышает 256 КиБ")
	}
	f, err := os.OpenFile(destination, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return errors.New("не удалось сохранить исходный файл")
	}
	n, copyErr := io.Copy(f, io.LimitReader(resp.Body, maxInput+1))
	closeErr := f.Close()
	if copyErr != nil || closeErr != nil {
		return errors.New("не удалось сохранить исходный файл")
	}
	if n > maxInput {
		return errors.New("исходный файл превышает 256 КиБ")
	}
	return nil
}

func (t *telegram) sendDocument(ctx context.Context, chat int64, path string) error {
	file, err := os.Open(path)
	if err != nil {
		return errors.New("не удалось открыть PNG")
	}
	defer file.Close()
	reader, writer := io.Pipe()
	multipartWriter := multipart.NewWriter(writer)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, t.endpoint("sendDocument"), reader)
	if err != nil {
		reader.Close()
		writer.Close()
		return errors.New("не удалось подготовить отправку PNG")
	}
	req.Header.Set("Content-Type", multipartWriter.FormDataContentType())
	done := make(chan struct{})
	go func() {
		defer close(done)
		err := multipartWriter.WriteField("chat_id", strconv.FormatInt(chat, 10))
		if err == nil {
			var part io.Writer
			part, err = multipartWriter.CreateFormFile("document", filepath.Base(path))
			if err == nil {
				_, err = io.Copy(part, file)
			}
		}
		if err == nil {
			err = multipartWriter.Close()
		}
		writer.CloseWithError(err)
	}()
	resp, requestErr := t.client.Do(req)
	// Закрытие reader разблокирует отправителя и при раннем ответе HTTP.
	reader.Close()
	<-done
	if requestErr != nil {
		return errors.New("ошибка отправки PNG в Telegram")
	}
	return t.response(resp, nil)
}

func outputFiles(dir string) ([]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, errors.New("не удалось прочитать результат")
	}
	paths := make([]string, 0, maxOutputs)
	var total int64
	for _, entry := range entries {
		if strings.ToLower(filepath.Ext(entry.Name())) != ".png" {
			continue
		}
		info, err := entry.Info()
		if err != nil || !info.Mode().IsRegular() {
			return nil, errors.New("некорректный PNG в результате")
		}
		total += info.Size()
		if len(paths) >= maxOutputs || total > maxOutputBytes {
			return nil, errors.New("результат превышает лимит: 10 PNG или 20 МиБ")
		}
		paths = append(paths, filepath.Join(dir, entry.Name()))
	}
	if len(paths) == 0 {
		return nil, errors.New("не удалось построить PNG; проверьте синтаксис C++")
	}
	return paths, nil
}

func render(ctx context.Context, executable, dir string) ([]string, error) {
	output := filepath.Join(dir, "output")
	cmd := exec.CommandContext(ctx, executable, "input.cpp", "--out", output, "--no-ui", "--no-html", "--for-style", "hexagon", "--detail", "study", "--checks", "hide", "--io-style", "symbols", "--page-height", "0", "--png", "2")
	cmd.Dir = dir
	for _, env := range os.Environ() {
		key, _, _ := strings.Cut(env, "=")
		switch key {
		case "TELEGRAM_BOT_TOKEN", "TMPDIR", "HOME", "XDG_CACHE_HOME", "PYTHONDONTWRITEBYTECODE":
		default:
			cmd.Env = append(cmd.Env, env)
		}
	}
	// Временные файлы и кэши дочерних процессов удаляются вместе с задачей.
	cmd.Env = append(cmd.Env, "TMPDIR="+dir, "HOME="+dir, "XDG_CACHE_HOME="+filepath.Join(dir, "cache"), "PYTHONDONTWRITEBYTECODE=1")
	// Вывод CLI не сохраняется: исходник и диагностика не попадают в логи.
	cmd.Stdout = io.Discard
	cmd.Stderr = io.Discard
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error { return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL) }
	cmd.WaitDelay = 2 * time.Second
	if err := cmd.Start(); err != nil {
		return nil, errors.New("не удалось запустить blockwright")
	}
	err := cmd.Wait()
	// Удаляем также потомков, оставшихся после завершения родителя.
	_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
	if ctx.Err() != nil {
		return nil, errors.New("обработка отменена или превысила 90 секунд")
	}
	if err != nil {
		return nil, errors.New("не удалось построить схему; проверьте синтаксис C++")
	}
	return outputFiles(output)
}

type bot struct {
	api        *telegram
	executable string
	mu         sync.Mutex
	active     map[int64]bool
	wg         sync.WaitGroup
}

func (b *bot) acquire(id int64) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.active[id] || len(b.active) >= 2 {
		return false
	}
	b.active[id] = true
	return true
}
func (b *bot) release(id int64) { b.mu.Lock(); defer b.mu.Unlock(); delete(b.active, id) }
func (b *bot) reply(ctx context.Context, chat int64, text string) {
	if err := b.api.sendText(ctx, chat, text); err != nil && ctx.Err() == nil {
		log.Printf("Не удалось отправить сообщение: %v", err)
	}
}

func (b *bot) handle(ctx context.Context, m *message) {
	if m == nil {
		return
	}
	if strings.HasPrefix(m.Text, "/start") {
		b.reply(ctx, m.Chat.ID, instruction)
		return
	}
	if m.Document == nil {
		b.reply(ctx, m.Chat.ID, instruction)
		return
	}
	doc := *m.Document
	ext := strings.ToLower(filepath.Ext(doc.FileName))
	if ext != ".cpp" && ext != ".cc" && ext != ".cxx" {
		b.reply(ctx, m.Chat.ID, "Нужен документ с расширением .cpp, .cc или .cxx.")
		return
	}
	if doc.FileSize < 0 || doc.FileSize > maxInput {
		b.reply(ctx, m.Chat.ID, "Размер исходного файла должен быть не больше 256 КиБ.")
		return
	}
	if m.From == nil || m.From.ID == 0 || doc.FileID == "" {
		b.reply(ctx, m.Chat.ID, "Не удалось определить отправителя или документ.")
		return
	}
	user := m.From.ID
	if !b.acquire(user) {
		b.reply(ctx, m.Chat.ID, "Обработка занята. Дождитесь результата предыдущей задачи и попробуйте снова.")
		return
	}
	b.wg.Add(1)
	go func() {
		defer b.wg.Done()
		defer b.release(user)
		taskCtx, cancel := context.WithTimeout(ctx, processingTimeout)
		defer cancel()
		err := b.process(taskCtx, m.Chat.ID, doc.FileID)
		if err != nil && ctx.Err() == nil {
			b.reply(ctx, m.Chat.ID, err.Error())
		}
	}()
}

func (b *bot) process(ctx context.Context, chat int64, fileID string) (resultErr error) {
	dir, err := os.MkdirTemp("", "blockwright-telegram-")
	if err != nil {
		return errors.New("не удалось создать временную папку")
	}
	defer func() {
		if err := os.RemoveAll(dir); err != nil {
			// PathError содержит локальный путь: в журнал и ответ уходит только общее сообщение.
			cleanupErr := errors.New("не удалось удалить временные файлы задачи")
			log.Print(cleanupErr)
			resultErr = errors.Join(resultErr, cleanupErr)
		}
	}()
	if err = b.api.download(ctx, fileID, filepath.Join(dir, "input.cpp")); err != nil {
		return err
	}
	paths, err := render(ctx, b.executable, dir)
	if err != nil {
		return err
	}
	for _, path := range paths {
		if err = b.api.sendDocument(ctx, chat, path); err != nil {
			return err
		}
	}
	return nil
}

func (b *bot) run(ctx context.Context) {
	defer b.wg.Wait()
	var offset int64
	for ctx.Err() == nil {
		var updates []update
		// Длинные Unicode-сообщения в пачке должны помещаться в maxAPIResponse.
		err := b.api.call(ctx, "getUpdates", map[string]any{"offset": offset, "timeout": 25, "limit": 10, "allowed_updates": []string{"message"}}, &updates)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			log.Printf("Ошибка получения обновлений: %v", err)
			timer := time.NewTimer(3 * time.Second)
			select {
			case <-ctx.Done():
				timer.Stop()
				return
			case <-timer.C:
			}
			continue
		}
		sort.Slice(updates, func(i, j int) bool { return updates[i].ID < updates[j].ID })
		for _, u := range updates {
			if ctx.Err() != nil {
				return
			}
			if u.ID < offset {
				continue
			}
			b.handle(ctx, u.Message)
			// Подтверждаем только после синхронного отказа или передачи в рабочую задачу.
			offset = u.ID + 1
		}
	}
}

func main() {
	token := os.Getenv("TELEGRAM_BOT_TOKEN")
	if !safeToken.MatchString(token) {
		log.Fatal("Задайте корректный TELEGRAM_BOT_TOKEN")
	}
	executable, err := exec.LookPath("blockwright")
	if err != nil {
		log.Fatal("blockwright не найден в PATH")
	}
	executable, err = filepath.Abs(executable)
	if err != nil {
		log.Fatal("Не удалось определить путь blockwright")
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	client := &http.Client{Timeout: 40 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	api := &telegram{token: token, base: "https://api.telegram.org", client: client}
	b := &bot{api: api, executable: executable, active: make(map[int64]bool)}
	log.Print("Telegram-бот запущен")
	b.run(ctx)
	log.Print("Telegram-бот остановлен")
}
