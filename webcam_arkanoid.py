import pygame
import cv2
import mediapipe as mp
import sys
import os
import json
import random

# --- Constants ---
WIDTH = 1280
HEIGHT = 720
FPS = 60

POWERUP_PROBABILITY = 0.35
POWERUP_FALL_SPEED = 5
BULLET_SPEED = -11
BULLET_WIDTH = 8
BULLET_HEIGHT = 24

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 50, 50)
GREEN = (50, 255, 50)
BLUE = (50, 50, 255)
CYAN = (0, 255, 255)

PADDLE_WIDTH = 180
PADDLE_HEIGHT = 32
BALL_RADIUS = 16

BRICK_ROWS = 5
BRICK_COLS = 11
BRICK_WIDTH = 80
BRICK_HEIGHT = 40
BRICK_PAD_X = (WIDTH - (BRICK_COLS * BRICK_WIDTH)) // (BRICK_COLS + 1)
BRICK_PAD_Y = 30
BRICK_OFFSET_Y = 90

HIGH_SCORE_FILE = "arkanoid_highscore.json"

ASSET_DIR = r"C:\Users\mehme\.gemini\antigravity\brain\b890358f-4b5b-469d-bff4-bba146f3273d"
_IMAGE_CACHE = {}

def load_img(filename, size=None, crop_hitbox=True):
    key = (filename, size, crop_hitbox)
    if key in _IMAGE_CACHE:
        return _IMAGE_CACHE[key]
        
    path = os.path.join(ASSET_DIR, filename)
    if os.path.exists(path):
        img = pygame.image.load(path).convert()
        if crop_hitbox:
            if size:
                img = pygame.transform.scale(img, size)
                
            # Clean AI compression artifacts (near-black to pure black)
            width, height = img.get_size()
            for x in range(width):
                for y in range(height):
                    c = img.get_at((x, y))
                    if c.r < 25 and c.g < 25 and c.b < 25:
                        img.set_at((x, y), (0,0,0))
                        
            img.set_colorkey((0,0,0))
            bounding_rect = img.get_bounding_rect()
            if bounding_rect.width > 0 and bounding_rect.height > 0:
                img = img.subsurface(bounding_rect).copy()
        else:
            if size:
                img = pygame.transform.scale(img, size)
                
        _IMAGE_CACHE[key] = img
        return img
    return None

class HandTracker:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        self.mp_draw = mp.solutions.drawing_utils
        self.cap = cv2.VideoCapture(0)
        
        if not self.cap.isOpened():
            raise RuntimeError("Error: Webcam could not be initialized.")

    def get_frame_and_hand(self):
        ret, frame = self.cap.read()
        if not ret:
            return None, None, False, -1

        # Flip horizontally for selfie-view
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_frame)
        
        is_fist = False
        is_thumbs_up = False
        fist_x = -1
        
        if results.multi_hand_landmarks:
            green_spec = self.mp_draw.DrawingSpec(color=(0, 0, 255), thickness=2, circle_radius=3)
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(
                    frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS,
                    landmark_drawing_spec=green_spec,
                    connection_drawing_spec=green_spec)
                
                lm = hand_landmarks.landmark
                
                index_folded = lm[8].y > lm[6].y
                middle_folded = lm[12].y > lm[10].y
                ring_folded = lm[16].y > lm[14].y
                pinky_folded = lm[20].y > lm[18].y
                
                thumb_up = lm[4].y < lm[3].y and lm[4].y < lm[5].y
                
                if index_folded and middle_folded and ring_folded and pinky_folded:
                    is_fist = True
                    if thumb_up:
                        is_thumbs_up = True
                
                # Use middle finger MCP x-coordinate as the center of the hand
                fist_x = lm[9].x
                break 
                
        return frame, results.multi_hand_landmarks, is_fist, is_thumbs_up, fist_x

    def release(self):
        self.cap.release()

class Brick(pygame.sprite.Sprite):
    def __init__(self, x, y, color, b_type='normal'):
        super().__init__()
        self.b_type = b_type
        self.color = color
        self.hp = 1
        
        if self.b_type == 'hard':
            self.hp = 2
            self.color = (150, 150, 150) # Gray
        elif self.b_type == 'unbreakable':
            self.hp = 5
            self.color = (60, 60, 60) # Dark Gray
            
        img = load_img("asteroid_brick_1774119655246.png", (BRICK_WIDTH, BRICK_HEIGHT))
        if img:
            self.image = img.copy()
            color_surface = pygame.Surface(self.image.get_size())
            color_surface.fill(self.color)
            self.image.blit(color_surface, (0,0), special_flags=pygame.BLEND_RGB_MULT)
            self.image.set_colorkey((0,0,0))
        else:
            self.image = pygame.Surface([BRICK_WIDTH, BRICK_HEIGHT])
            self.image.fill(self.color)
            
        if self.b_type == 'unbreakable':
            pygame.draw.rect(self.image, (200, 200, 200), self.image.get_rect(), 2)
            
        self.rect = self.image.get_rect()
        self.rect.centerx = x + BRICK_WIDTH // 2
        self.rect.centery = y + BRICK_HEIGHT // 2
        self.has_level_skip = False

    def hit(self):
        self.hp -= 1
        if self.hp <= 0:
            return True
        else:
            if self.b_type == 'hard':
                self.color = (200, 200, 200) # Lighter
            elif self.b_type == 'unbreakable':
                val = 60 + (5 - self.hp) * 35
                self.color = (val, val, val)
                
            img = load_img("asteroid_brick_1774119655246.png", (BRICK_WIDTH, BRICK_HEIGHT))
            if img:
                self.image = img.copy()
                color_surface = pygame.Surface(self.image.get_size())
                color_surface.fill(self.color)
                self.image.blit(color_surface, (0,0), special_flags=pygame.BLEND_RGB_MULT)
                self.image.set_colorkey((0,0,0))
            else:
                self.image.fill(self.color)
                
            if self.b_type == 'unbreakable':
                pygame.draw.rect(self.image, (200, 200, 200), self.image.get_rect(), 2)
            return False

class PowerUp(pygame.sprite.Sprite):
    def __init__(self, x, y, p_type):
        super().__init__()
        self.p_type = p_type
        
        img = None
        if self.p_type == 'gun':
            img = load_img("icon_gun_1774120294780.png", (48, 48))
        elif self.p_type == 'expand':
            img = load_img("icon_expand_1774120307262.png", (48, 48))
        elif self.p_type == 'multiball':
            img = load_img("icon_multiball_1774120320952.png", (48, 48))
        elif self.p_type == 'level_skip':
            img = load_img("icon_skip_1774120334425.png", (54, 54))

        if img:
            self.image = img
        else:
            self.image = pygame.Surface([24, 24])
            if self.p_type == 'gun': self.image.fill(GREEN)
            elif self.p_type == 'expand': self.image.fill((255, 255, 0))
            elif self.p_type == 'multiball': self.image.fill((255, 165, 0))
            elif self.p_type == 'level_skip': self.image.fill((128, 0, 128))

        self.rect = self.image.get_rect()
        self.rect.centerx = x
        self.rect.centery = y

    def update(self):
        if self.p_type == 'level_skip':
            self.rect.y += POWERUP_FALL_SPEED * 2.5
        else:
            self.rect.y += POWERUP_FALL_SPEED

class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        img = load_img("laser_bullet_1774120349060.png", (12, 40))
        if img:
            self.image = img
        else:
            self.image = pygame.Surface([BULLET_WIDTH, BULLET_HEIGHT])
            self.image.fill(CYAN)
        self.rect = self.image.get_rect()
        self.rect.centerx = x
        self.rect.bottom = y

    def update(self):
        self.rect.y += BULLET_SPEED

class BossBullet(pygame.sprite.Sprite):
    def __init__(self, x, y):
        super().__init__()
        img = load_img("laser_bullet_1774120349060.png", (12, 40))
        if img:
            self.image = pygame.transform.flip(img, False, True).copy()
            color_surface = pygame.Surface(self.image.get_size())
            color_surface.fill((255, 50, 50))
            self.image.blit(color_surface, (0,0), special_flags=pygame.BLEND_RGB_MULT)
            self.image.set_colorkey((0,0,0))
        else:
            self.image = pygame.Surface([BULLET_WIDTH, BULLET_HEIGHT])
            self.image.fill(RED)
        self.rect = self.image.get_rect()
        self.rect.centerx = x
        self.rect.top = y

    def update(self):
        self.rect.y += abs(BULLET_SPEED) - 1

class Paddle(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.current_width = PADDLE_WIDTH
        self._update_image()
        self.rect = self.image.get_rect()
        self.rect.x = WIDTH // 2 - self.current_width // 2
        self.rect.y = HEIGHT - 65
        self.gun_active_until = 0
        self.expand_active_until = 0
        self.last_shot_time = 0

    def _update_image(self):
        img = load_img("hover_platform_1774120092648.png", (self.current_width, PADDLE_HEIGHT + 10))
        if img:
            self.image = img
        else:
            self.image = pygame.Surface([self.current_width, PADDLE_HEIGHT])
            self.image.fill(CYAN)

    def set_width(self, width):
        if self.current_width != width:
            self.current_width = width
            old_center = self.rect.centerx
            self._update_image()
            self.rect = self.image.get_rect()
            self.rect.y = HEIGHT - 65
            self.rect.centerx = old_center

    def activate_gun(self):
        self.gun_active_until = pygame.time.get_ticks() + 5000

    def activate_expand(self):
        self.expand_active_until = pygame.time.get_ticks() + 10000
        self.set_width(PADDLE_WIDTH + 120)

    def update_abilities(self):
        now = pygame.time.get_ticks()
        if self.current_width > PADDLE_WIDTH and now > self.expand_active_until:
            self.set_width(PADDLE_WIDTH)

    def can_shoot(self):
        now = pygame.time.get_ticks()
        if now < self.gun_active_until and now - self.last_shot_time > 300:
            self.last_shot_time = now
            return True
        return False

    def update_position(self, target_x):
        """ Smoothly map raw hand x-coordinate (0 to 1) to paddle screen position """
        target_center_x = target_x * WIDTH
        current_center_x = self.rect.x + self.current_width / 2
        
        # Linear interpolation for smoothness
        new_center_x = current_center_x + (target_center_x - current_center_x) * 0.3
        
        self.rect.x = int(new_center_x - self.current_width / 2)
        
        # Ensure paddle stays within the screen
        if self.rect.left < 0:
            self.rect.left = 0
        if self.rect.right > WIDTH:
            self.rect.right = WIDTH

class Boss(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        img = load_img("boss_ship_1774119673738.png", (320, 96))
        if img:
            self.image = img
        else:
            self.image = pygame.Surface([320, 96])
            self.image.fill((200, 0, 200)) # PURPLE
        self.rect = self.image.get_rect()
        self.rect.centerx = WIDTH // 2
        self.rect.y = 50
        self.speed_x = 5
        self.hp = 100
        self.max_hp = 100
        
        self.last_burst_time = pygame.time.get_ticks()
        self.burst_delay = 2800 # Time between bursts
        self.shots_to_fire = 0
        self.last_shot_time = 0
        self.shot_delay = 180 # Time between rapid shots
        self.hits_since_drop = 0

    def update(self, boss_bullets=None, all_sprites=None):
        self.rect.x += self.speed_x
        
        if self.rect.left <= 0 and self.speed_x < 0:
            self.speed_x = -self.speed_x
        elif self.rect.right >= WIDTH and self.speed_x > 0:
            self.speed_x = -self.speed_x
            
        now = pygame.time.get_ticks()
        if self.shots_to_fire == 0 and now - self.last_burst_time > self.burst_delay:
            self.shots_to_fire = 1 # Fire a single tight cluster
            self.last_burst_time = now
            
        if self.shots_to_fire > 0 and now - self.last_shot_time > self.shot_delay:
            self.last_shot_time = now
            self.shots_to_fire -= 1
            if self.hp > 0 and boss_bullets is not None and all_sprites is not None:
                b1 = BossBullet(self.rect.left + 24, self.rect.bottom)
                b2 = BossBullet(self.rect.left + 48, self.rect.bottom)
                b3 = BossBullet(self.rect.right - 24, self.rect.bottom)
                b4 = BossBullet(self.rect.right - 48, self.rect.bottom)
                all_sprites.add(b1, b2, b3, b4)
                boss_bullets.add(b1, b2, b3, b4)

    def draw_hp(self, surface):
        if self.hp > 0:
            pct = self.hp / self.max_hp
            pygame.draw.rect(surface, RED, (self.rect.x, self.rect.y - 15, self.rect.width, 10))
            pygame.draw.rect(surface, GREEN, (self.rect.x, self.rect.y - 15, self.rect.width * pct, 10))

class Ball(pygame.sprite.Sprite):
    def __init__(self, x=None, y=None, speed_x=5, speed_y=-5, attached=False):
        super().__init__()
        img = load_img("energy_ball_1774119640797.png", (BALL_RADIUS * 2, BALL_RADIUS * 2))
        if img:
            self.image = img
        else:
            self.image = pygame.Surface([BALL_RADIUS * 2, BALL_RADIUS * 2], pygame.SRCALPHA)
            pygame.draw.circle(self.image, RED, (BALL_RADIUS, BALL_RADIUS), BALL_RADIUS)
        self.rect = self.image.get_rect()
        self.attached = attached
        if x is not None and y is not None:
            self.rect.centerx = x
            self.rect.centery = y
            self.speed_x = speed_x
            self.speed_y = speed_y
        else:
            self.reset()

    def reset(self):
        self.attached = True
        self.speed_x = 0
        self.speed_y = 0
        self.rect.centerx = WIDTH // 2
        self.rect.centery = HEIGHT // 2

    def update(self, paddle=None):
        if getattr(self, 'attached', False) and paddle is not None:
            self.rect.centerx = paddle.rect.centerx
            self.rect.bottom = paddle.rect.top - 2
            return
            
        self.rect.x += self.speed_x
        self.rect.y += self.speed_y

        # Bounce off walls
        if self.rect.left <= 0 and self.speed_x < 0:
            self.speed_x = -self.speed_x
        if self.rect.right >= WIDTH and self.speed_x > 0:
            self.speed_x = -self.speed_x
        if self.rect.top <= 0 and self.speed_y < 0:
            self.speed_y = -self.speed_y

def get_high_score():
    if os.path.exists(HIGH_SCORE_FILE):
        try:
            with open(HIGH_SCORE_FILE, "r") as f:
                data = json.load(f)
                return data.get("high_score", 0)
        except:
            return 0
    return 0

def save_high_score(score):
    with open(HIGH_SCORE_FILE, "w") as f:
        json.dump({"high_score": score}, f)

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Webcam Controlled Arkanoid")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont(None, 48)
    large_font = pygame.font.SysFont(None, 96)

    try:
        tracker = HandTracker()
    except Exception as e:
        print(f"Failed to initialize webcam tracker: {e}")
        pygame.quit()
        sys.exit()

    all_sprites = pygame.sprite.Group()
    bricks = pygame.sprite.Group()
    powerups = pygame.sprite.Group()
    bullets = pygame.sprite.Group()
    boss_bullets = pygame.sprite.Group()
    balls = pygame.sprite.Group()
    bosses = pygame.sprite.Group()
    level = 1

    paddle = Paddle()
    initial_ball = Ball()
    all_sprites.add(paddle)
    all_sprites.add(initial_ball)
    balls.add(initial_ball)

    # Bricks color palette
    colors = [(255, 99, 71), (255, 165, 0), (255, 215, 0), (50, 205, 50), (30, 144, 255)]

    LEVEL_LAYOUTS = {
        1: [
            " NNNNNNNN ",
            "  NNNNNN  ",
            "   NNNN   ",
            "    NN    "
        ],
        2: [
            "N H N H N ",
            "H N H N H ",
            "N H N H N ",
            "H N H N H ",
            "N H N H N "
        ],
        3: [
            "  N     N  ",
            "   N   N   ",
            "  NNNNNNN  ",
            " NN NNN NN ",
            "NNNNNNNNNNN",
            "N NNNNNNN N",
            "N N     N N",
            "  NN   NN  "
        ],
        4: [
            "    NN    ",
            "   HNNH   ",
            "  HHNNHH  ",
            " UHHNNHHU ",
            "  HHNNHH  ",
            "   HNNH   ",
            "    NN    "
        ],
        5: [
            "H U    U H",
            "H N    N H",
            "H        H",
            "H NNNNNN H",
            "H U    U H"
        ]
    }

    def start_level():
        for b in bricks: b.kill()
        for b in bosses: b.kill()
        
        if level <= 5:
            layout = LEVEL_LAYOUTS[level]
            max_cols = max(len(row) for row in layout)
            current_pad_x = (WIDTH - (max_cols * BRICK_WIDTH)) // (max_cols + 1)
            
            for row_idx, row_str in enumerate(layout):
                color = colors[row_idx % len(colors)]
                for col_idx, char in enumerate(row_str):
                    if char == ' ':
                        continue
                        
                    b_type = 'normal'
                    if char == 'H':
                        b_type = 'hard'
                    elif char == 'U':
                        b_type = 'unbreakable'
                        
                    x = current_pad_x + col_idx * (BRICK_WIDTH + current_pad_x)
                    y = BRICK_OFFSET_Y + row_idx * (BRICK_HEIGHT + BRICK_PAD_Y)
                    brick = Brick(x, y, color, b_type)
                    all_sprites.add(brick)
                    bricks.add(brick)
            
            if len(bricks) > 0:
                random.choice(bricks.sprites()).has_level_skip = True
        elif level == 6:
            b = Boss()
            all_sprites.add(b)
            bosses.add(b)

    start_level()

    score = 0
    high_score = get_high_score()
    game_over = False
    display_webcam = False

    bg_img = load_img("space_bg_1774119704585.png", (WIDTH, HEIGHT), crop_hitbox=False)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and game_over:
                    game_over = False
                    score = 0
                    level = 1
                    for b in balls: b.kill()
                    initial_ball = Ball()
                    all_sprites.add(initial_ball)
                    balls.add(initial_ball)
                    paddle.gun_active_until = 0
                    paddle.expand_active_until = 0
                    paddle.set_width(PADDLE_WIDTH)
                    for b in bricks: b.kill()
                    for p in powerups: p.kill()
                    for b in bullets: b.kill()
                    for bb in boss_bullets: bb.kill()
                    start_level()
                elif event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_w:
                    display_webcam = not display_webcam
                elif event.key == pygame.K_n and not game_over:
                    if level <= 5:
                        level += 1
                        for b in balls: b.kill()
                        new_b = Ball()
                        all_sprites.add(new_b)
                        balls.add(new_b)
                        paddle.gun_active_until = 0
                        paddle.expand_active_until = 0
                        paddle.set_width(PADDLE_WIDTH)
                        for p in powerups: p.kill()
                        for b in bullets: b.kill()
                        for bb in boss_bullets: bb.kill()
                        start_level()

        # Read webcam
        frame, hand_landmarks, is_fist, is_thumbs_up, fist_x = tracker.get_frame_and_hand()
        
        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:
            is_thumbs_up = True

        if not game_over:
            # Control logic: only move if fist is detected
            if is_fist and fist_x != -1:
                paddle.update_position(fist_x)
                
            if is_thumbs_up:
                for current_ball in balls:
                    if getattr(current_ball, 'attached', False):
                        current_ball.attached = False
                        current_ball.speed_y = -8
                        current_ball.speed_x = random.choice([-7, 7])

            paddle.update_abilities()
            
            # Boss waits for the player to launch the ball before engaging
            if not all(getattr(b, 'attached', False) for b in balls):
                bosses.update(boss_bullets, all_sprites)
                
            boss_bullets.update()
            
            for bb in boss_bullets:
                if bb.rect.top > HEIGHT:
                    bb.kill()

            if pygame.sprite.spritecollideany(paddle, boss_bullets):
                game_over = True
                save_high_score(high_score)

            for current_ball in balls:
                current_ball.update(paddle)
                if getattr(current_ball, 'attached', False):
                    continue
                # Ball/Paddle collision
                if pygame.sprite.collide_rect(current_ball, paddle):
                    if current_ball.speed_y > 0: # Only bounce if it's falling downwards
                        rel_x = (current_ball.rect.centerx - paddle.rect.centerx) / (paddle.current_width / 2)
                        current_ball.speed_x = rel_x * 6 
                        
                        if abs(current_ball.speed_x) < 1.0:
                            current_ball.speed_x = 1.0 if current_ball.speed_x >= 0 else -1.0
                            
                        current_ball.speed_y = -abs(current_ball.speed_y)
                        current_ball.rect.bottom = paddle.rect.top

                # Ball/Brick collision
                hit_bricks = pygame.sprite.spritecollide(current_ball, bricks, False)
                if hit_bricks:
                    current_ball.speed_y = -current_ball.speed_y
                    
                    for brick in hit_bricks:
                        destroyed = brick.hit()
                        if destroyed:
                            brick.kill()
                            score += 10
                            if score > high_score:
                                high_score = score
                            
                            if brick.has_level_skip:
                                p = PowerUp(brick.rect.centerx, brick.rect.centery, 'level_skip')
                                all_sprites.add(p)
                                powerups.add(p)
                            elif random.random() < POWERUP_PROBABILITY:
                                p_type = random.choice(['gun', 'expand', 'multiball'])
                                p = PowerUp(brick.rect.centerx, brick.rect.centery, p_type)
                                all_sprites.add(p)
                                powerups.add(p)

                # Ball/Boss collision
                hit_bosses = pygame.sprite.spritecollide(current_ball, bosses, False)
                for boss in hit_bosses:
                    if current_ball.rect.bottom > boss.rect.top and current_ball.rect.top < boss.rect.bottom:
                        current_ball.speed_y = -current_ball.speed_y
                    boss.hp -= 1
                    boss.hits_since_drop += 1
                    if boss.hits_since_drop >= 3:
                        boss.hits_since_drop = 0
                        p_type = random.choice(['gun', 'expand', 'multiball'])
                        p = PowerUp(boss.rect.centerx, boss.rect.centery, p_type)
                        all_sprites.add(p)
                        powerups.add(p)
                        
                    if boss.hp <= 0:
                        boss.kill()
                        score += 1000
                        if score > high_score: high_score = score

                if current_ball.rect.bottom >= HEIGHT:
                    current_ball.kill()

            if len(balls) == 0:
                game_over = True
                save_high_score(high_score)

            # Level Progression check
            if level <= 5 and len(bricks) == 0:
                level += 1
                for b in balls: b.kill()
                new_b = Ball()
                all_sprites.add(new_b)
                balls.add(new_b)
                paddle.gun_active_until = 0
                paddle.expand_active_until = 0
                paddle.set_width(PADDLE_WIDTH)
                for p in powerups: p.kill()
                for b in bullets: b.kill()
                for bb in boss_bullets: bb.kill()
                start_level()
            elif level == 6 and len(bosses) == 0 and not game_over:
                game_over = True

            # --- PowerUps & Bullets Logic ---
            powerups.update()
            bullets.update()

            for p in powerups:
                if p.rect.top > HEIGHT:
                    p.kill()
            for b in bullets:
                if b.rect.bottom < 0:
                    b.kill()

            caught_powerups = pygame.sprite.spritecollide(paddle, powerups, True)
            for p in caught_powerups:
                if p.p_type == 'gun':
                    paddle.activate_gun()
                elif p.p_type == 'expand':
                    paddle.activate_expand()
                elif p.p_type == 'multiball':
                    new_ball = Ball(x=paddle.rect.centerx, y=paddle.rect.top - BALL_RADIUS*2, speed_x=random.choice([-7, 7]), speed_y=-8)
                    all_sprites.add(new_ball)
                    balls.add(new_ball)
                elif p.p_type == 'level_skip':
                    if level <= 5:
                        level += 1
                        for b in balls: b.kill()
                        new_b = Ball()
                        all_sprites.add(new_b)
                        balls.add(new_b)
                        paddle.gun_active_until = 0
                        paddle.expand_active_until = 0
                        paddle.set_width(PADDLE_WIDTH)
                        for curr_p in powerups: curr_p.kill()
                        for curr_b in bullets: curr_b.kill()
                        for bb in boss_bullets: bb.kill()
                        start_level()
                        break

            if paddle.can_shoot():
                b1 = Bullet(paddle.rect.left + 32, paddle.rect.top)
                b2 = Bullet(paddle.rect.right - 32, paddle.rect.top)
                all_sprites.add(b1, b2)
                bullets.add(b1, b2)

            # Bullet/Brick collision
            for b in bullets:
                hit_by_bullet = pygame.sprite.spritecollide(b, bricks, False)
                if hit_by_bullet:
                    b.kill()
                    for brick in hit_by_bullet:
                        destroyed = brick.hit()
                        if destroyed:
                            brick.kill()
                            score += 10
                            if score > high_score:
                                high_score = score
                            if brick.has_level_skip:
                                p = PowerUp(brick.rect.centerx, brick.rect.centery, 'level_skip')
                                all_sprites.add(p)
                                powerups.add(p)
                            elif random.random() < POWERUP_PROBABILITY:
                                p_type = random.choice(['gun', 'expand', 'multiball'])
                                p = PowerUp(brick.rect.centerx, brick.rect.centery, p_type)
                                all_sprites.add(p)
                                powerups.add(p)
                
                # Bullet/Boss collision
                hit_bosses = pygame.sprite.spritecollide(b, bosses, False)
                for boss in hit_bosses:
                    b.kill()
                    boss.hp -= 1
                    boss.hits_since_drop += 1
                    if boss.hits_since_drop >= 3:
                        boss.hits_since_drop = 0
                        p_type = random.choice(['gun', 'expand', 'multiball'])
                        p = PowerUp(boss.rect.centerx, boss.rect.centery, p_type)
                        all_sprites.add(p)
                        powerups.add(p)
                        
                    if boss.hp <= 0:
                        boss.kill()
                        score += 1000
                        if score > high_score: high_score = score

        # Rendering
        if display_webcam and frame is not None:
            # Fullscreen webcam background
            resized_frame = cv2.resize(frame, (WIDTH, HEIGHT))
            rgb_bg = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
            bg_surface = pygame.image.frombuffer(rgb_bg.tobytes(), (WIDTH, HEIGHT), "RGB")
            screen.blit(bg_surface, (0, 0))
        elif bg_img:
            screen.blit(bg_img, (0, 0))
        else:
            screen.fill(BLACK)

        all_sprites.draw(screen)

        for boss in bosses:
            boss.draw_hp(screen)

        level_text = font.render(f"Level: {level}", True, WHITE)
        screen.blit(level_text, (WIDTH // 2 - level_text.get_width() // 2, 30))

        score_text = font.render(f"Score: {score}", True, WHITE)
        high_score_text = font.render(f"High Score: {high_score}", True, WHITE)
        screen.blit(score_text, (30, 30))
        screen.blit(high_score_text, (WIDTH - high_score_text.get_width() - 30, 30))

        if game_over:
            if level == 6 and len(bosses) == 0:
                go_text = large_font.render("YOU WIN!!", True, GREEN)
            else:
                go_text = large_font.render("GAME OVER", True, RED)
            restart_text = font.render("Press 'R' to Restart", True, WHITE)
            screen.blit(go_text, (WIDTH // 2 - go_text.get_width() // 2, HEIGHT // 2 - 40))
            screen.blit(restart_text, (WIDTH // 2 - restart_text.get_width() // 2, HEIGHT // 2 + 40))

        # Gesture indicator
        if is_fist:
            fist_text = font.render("FIST!", True, GREEN)
            screen.blit(fist_text, (WIDTH // 2 - fist_text.get_width() // 2, HEIGHT - 35))
        else:
            open_text = font.render("OPEN", True, RED)
            screen.blit(open_text, (WIDTH // 2 - open_text.get_width() // 2, HEIGHT - 35))

        pygame.display.flip()
        clock.tick(FPS)

    tracker.release()
    pygame.quit()

if __name__ == "__main__":
    main()
