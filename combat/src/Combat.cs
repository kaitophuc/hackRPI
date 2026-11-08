using System;
using System.Collections.Generic;

namespace Flighting {
public sealed class EnemyFighter {
    public int Id,FireCooldown;
    public Aircraft Body=new Aircraft();
    public V3 Previous;
    public bool Passing;
}
public sealed class Projectile {
    public V3 Position,Velocity;
    public bool Hostile;
    public int Damage,Age;
}
public sealed class HitBurst {
    public V3 Position;
    public int Age;
}
// Combat consumes exactly the same fixed simulation ticks as flight. No renderer,
// wall clock, platform input, or framework PRNG participates in its decisions.
public sealed class CombatState {
    public List<EnemyFighter> Enemies=new List<EnemyFighter>();
    public List<Projectile> Shots=new List<Projectile>();
    public List<HitBurst> Bursts=new List<HitBurst>();
    public long Tick;
    public int Kills,Wave,FireCooldown,WaveCooldown,NextEnemyId,ShotsFired,HitsTaken,LastDamage,HitFlash;
    public bool GameOver;
    public uint RandomState;
    public const uint FireButton=4,RestartButton=8;
    public const int MaxEnemies=4,MaxShots=192;
    public CombatState() { }
    public CombatState(uint seed) {RandomState=seed^0x9e3779b9u;if(RandomState==0)RandomState=1;}
    uint Next() {unchecked {uint x=RandomState;x^=x<<13;x^=x>>17;x^=x<<5;return RandomState=x;}}
    public void Step(Aircraft player,InputState input,World world,V3 previousPlayer,V3 scroll=default(V3)) {
        if(GameOver)return;
        // Convert existing actors and the previous player position into the new
        // scrolling frame before spawning anything. Swept collision endpoints
        // then share one coordinate system; newly spawned actors are not shifted twice.
        if(scroll.X!=0||scroll.Y!=0||scroll.Z!=0) {
            foreach(EnemyFighter enemy in Enemies)enemy.Body.Position+=scroll;
            foreach(Projectile shot in Shots)shot.Position+=scroll;
            foreach(HitBurst burst in Bursts)burst.Position+=scroll;
            previousPlayer+=scroll;
        }
        Tick++;if(HitFlash>0)HitFlash--;
        for(int i=Bursts.Count-1;i>=0;i--)if(++Bursts[i].Age>35)Bursts.RemoveAt(i);
        if(--WaveCooldown<=0) {SpawnWave(player,world);WaveCooldown=300;}
        V3 playerVelocity=(player.Position-previousPlayer)*60;
        if(FireCooldown>0)FireCooldown--;
        if((input.buttons&FireButton)!=0&&FireCooldown==0) {
            if(Shots.Count<MaxShots) {
                V3 muzzle=player.Position+player.Forward*2+player.Right*((ShotsFired&1)==0?-1.1:1.1);
                V3 aim=player.Position+player.Forward*120;
                Shots.Add(new Projectile {Position=muzzle,Velocity=(aim-muzzle).Unit*190+playerVelocity});ShotsFired++;
            }
            FireCooldown=8;
        }
        for(int i=Enemies.Count-1;i>=0;i--) {
            EnemyFighter enemy=Enemies[i];enemy.Previous=enemy.Body.Position;
            V3 offset=player.Position-enemy.Body.Position;double distance=offset.Length;
            if(distance>420||(enemy.Passing&&V3.Dot(enemy.Body.Position-player.Position,player.Forward)<-150)) {Enemies.RemoveAt(i);continue;}
            if(distance<28)enemy.Passing=true;
            V3 direction=enemy.Body.Forward;
            if(!enemy.Passing)direction=(direction*.985+offset.Unit*.015).Unit;
            enemy.Body.Yaw=Math.Atan2(direction.X,-direction.Z);enemy.Body.Pitch=Math.Asin(Aircraft.Clamp(direction.Y,-1,1));
            enemy.Body.Position+=direction*(38.0/60);
            enemy.Body.Position.Y=Math.Max(world.Height(enemy.Body.Position.X,enemy.Body.Position.Z)+5,enemy.Body.Position.Y);
            if(--enemy.FireCooldown<=0&&!enemy.Passing&&distance<230&&Shots.Count<MaxShots) {
                // Lead the current flight path once; projectiles never home after firing.
                V3 target=player.Position+playerVelocity*(distance/77.5);
                V3 muzzle=enemy.Body.Position+direction*3;
                // Halve the complete enemy bullet velocity, including inherited motion.
                Shots.Add(new Projectile {Position=muzzle,Velocity=((target-muzzle).Unit*125+direction*38)*.5,Hostile=true,Damage=5+(int)(Next()%6)});
                enemy.FireCooldown=85+(int)(Next()%30);
            }
        }
        for(int i=Shots.Count-1;i>=0;i--) {
            Projectile shot=Shots[i];V3 start=shot.Position;shot.Position+=shot.Velocity*(1.0/60);shot.Age++;
            bool consumed=false;
            if(shot.Hostile) {
                double impact;
                if(SegmentHit(start-previousPlayer,shot.Position-player.Position,1.4,out impact)) {DamagePlayer(player,shot.Damage);consumed=true;}
            } else {
                int target=-1;double earliest=2;
                for(int j=0;j<Enemies.Count;j++) {
                    double impact;EnemyFighter enemy=Enemies[j];
                    if(SegmentHit(start-enemy.Previous,shot.Position-enemy.Body.Position,3.1,out impact)&&impact<earliest) {earliest=impact;target=j;}
                }
                if(target>=0) {
                    if(Bursts.Count<16)Bursts.Add(new HitBurst {Position=Enemies[target].Body.Position});
                    Enemies.RemoveAt(target);Kills++;consumed=true;
                }
            }
            if(consumed||shot.Age>=240||shot.Position.Y<world.Height(shot.Position.X,shot.Position.Z))Shots.RemoveAt(i);
            if(GameOver)break;
        }
    }
    void SpawnWave(Aircraft player,World world) {
        if(Enemies.Count>=MaxEnemies)return;
        Wave++;
        for(int lane=0;lane<3&&Enemies.Count<MaxEnemies;lane++) {
            double side=lane==0?0:lane==1?-18:18,height=lane==0?0:lane==1?7:-5;
            V3 p=player.Position+player.Forward*(lane==0?125:155)+player.Right*side+new V3(0,height,0);
            p.Y=Math.Max(p.Y,world.Height(p.X,p.Z)+8);V3 heading=(player.Position-p).Unit;
            var enemy=new EnemyFighter {Id=NextEnemyId++,FireCooldown=35+lane*18,Previous=p};
            enemy.Body.Position=p;enemy.Body.Yaw=Math.Atan2(heading.X,-heading.Z);enemy.Body.Pitch=Math.Asin(heading.Y);enemy.Body.Speed=38;enemy.Body.Health=1;
            Enemies.Add(enemy);
        }
    }
    public void DamagePlayer(Aircraft player,int damage) {
        if(GameOver||damage<=0)return;
        player.Health=Math.Max(0,player.Health-damage);HitsTaken++;LastDamage=damage;HitFlash=14;
        if(player.Health==0)GameOver=true;
    }
    // Swept collision against a moving target, including shots that cross a target
    // entirely within a single tick. Return the earliest intersection parameter.
    public static bool SegmentHit(V3 start,V3 end,double radius,out double impact) {
        impact=0;double c=V3.Dot(start,start)-radius*radius;if(c<=0)return true;
        V3 delta=end-start;double a=V3.Dot(delta,delta);if(a<1e-12)return false;
        double b=V3.Dot(start,delta),disc=b*b-a*c;if(disc<0)return false;
        impact=(-b-Math.Sqrt(disc))/a;return impact>=0&&impact<=1;
    }
    public string Summary(Aircraft player) {
        return String.Join(",",new object[]{Tick,player.Health,Kills,Wave,Enemies.Count,Shots.Count,ShotsFired,HitsTaken,GameOver?1:0,RandomState});
    }
}
}
